"""Claude Code CLI provider implementation."""

import asyncio
import codecs
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator

from ...config import get_settings
from ...utils.content import extract_content
from ...utils.subprocess import create_subprocess
from ..base import BaseProvider


logger = logging.getLogger(__name__)

# Threshold above which system_prompt is passed via --system-prompt-file instead
# of --system-prompt argv. Linux kernel MAX_ARG_STRLEN is 128 KiB per argv slot;
# 100 KiB leaves margin for other args + env. Hitting the limit causes execve
# to fail with [Errno 7] Argument list too long.
_SYSTEM_PROMPT_ARGV_LIMIT = 100 * 1024

# Isolated HOME for the spawned CLI. Prevents the real $HOME/CLAUDE.md and the
# host user's memory files from being pulled into bridge-backed chat sessions.
# Off by default; enable by setting BRIDGE_ISOLATE_HOME=1. Credentials from
# the real $HOME/.claude/ are symlinked into the isolated home on first use.
_BRIDGE_HOME_READY: Path | None = None
_BRIDGE_HOME_INIT_FAILED = False


def _isolated_bridge_home() -> Path | None:
    """Return the isolated HOME path for the bridge CLI, or None if disabled/unusable.

    Initialises the directory on first call (idempotent). Failures fall back to
    ``None`` so the caller spawns CLI with the inherited HOME — no regression.
    """
    global _BRIDGE_HOME_READY, _BRIDGE_HOME_INIT_FAILED
    if _BRIDGE_HOME_READY is not None:
        return _BRIDGE_HOME_READY
    if _BRIDGE_HOME_INIT_FAILED:
        return None
    if os.environ.get("BRIDGE_ISOLATE_HOME", "").strip() not in ("1", "true", "yes", "on"):
        _BRIDGE_HOME_INIT_FAILED = True
        return None

    home_path = Path(os.environ.get("BRIDGE_ISOLATED_HOME", "/var/lib/ai-secretary-bridge"))
    real_claude = Path(os.path.expanduser("~/.claude"))

    try:
        (home_path / ".claude").mkdir(parents=True, exist_ok=True)
        # Sandbox cwd lives inside the isolated home so the CLI's CLAUDE.md
        # search (which walks up from cwd) never reaches /root/CLAUDE.md.
        (home_path / "sandbox").mkdir(parents=True, exist_ok=True)
        # Empty marker CLAUDE.md so the CLI's memory search stops here and does
        # not keep walking up to the real /root/CLAUDE.md.
        marker = home_path / "CLAUDE.md"
        if not marker.exists():
            marker.write_text("", encoding="utf-8")
        # Symlink credentials + settings so the CLI can still authenticate.
        for name in (".credentials.json", "settings.json"):
            src = real_claude / name
            dst = home_path / ".claude" / name
            if src.exists() and not dst.exists():
                try:
                    dst.symlink_to(src)
                except OSError:
                    # Fall back to copy if symlink is refused (e.g. cross-device).
                    dst.write_bytes(src.read_bytes())
    except OSError as exc:
        logger.warning("Bridge HOME isolation disabled — setup failed: %s", exc)
        _BRIDGE_HOME_INIT_FAILED = True
        return None

    _BRIDGE_HOME_READY = home_path
    logger.info("Bridge CLI runs with isolated HOME=%s", home_path)
    return home_path


def _build_cli_env() -> dict[str, str] | None:
    """Build env dict for the CLI subprocess. Returns None to inherit os.environ."""
    home = _isolated_bridge_home()
    if home is None:
        return None
    env = os.environ.copy()
    env["HOME"] = str(home)
    return env


def _cli_cwd() -> str | None:
    """Sandbox cwd for the CLI subprocess, kept outside the host user's $HOME
    so the CLAUDE.md lookup (which walks up from cwd) cannot reach it.
    Returns None to let ``create_subprocess`` pick its default sandbox."""
    home = _isolated_bridge_home()
    return str(home / "sandbox") if home else None


class ClaudeProvider(BaseProvider):
    """Provider for Claude Code CLI.

    Note: Claude Code is an agentic CLI tool, not a direct LLM wrapper.
    Some OpenAI parameters (temperature, top_p, top_k) are not supported
    as they're not exposed by the CLI.

    Supported parameters:
    - model: Model alias ('sonnet', 'opus') or full name
    - system_prompt: System prompt for the session
    - stream: Via --output-format stream-json
    - thinking: Via trigger keywords in prompt (workaround)

    Thinking Mode (via keywords):
    Claude Code responds to specific keywords that trigger extended thinking:
    - "think" → ~4,000 tokens
    - "think hard" → ~10,000 tokens
    - "ultrathink" → ~31,999 tokens
    """

    name = "claude"

    # Model names supported by Claude Code
    # Aliases (resolve to latest version)
    MODEL_ALIASES = ["sonnet", "opus", "haiku"]

    # Default model list (used if CLAUDE_MODELS env var is empty)
    DEFAULT_MODELS = [
        # Aliases (recommended - always latest)
        "sonnet",
        "opus",
        "haiku",
        # Claude 4.5 (latest)
        "claude-sonnet-4-5-20250929",
        "claude-opus-4-5-20251101",
        "claude-haiku-4-5-20251001",
        # Claude 4.1
        "claude-opus-4-1-20250805",
        # Claude 3.5
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        # Claude 3
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    ]

    # Thinking keywords mapped to approximate token budgets
    THINKING_KEYWORDS = {
        "low": "think",  # ~4,000 tokens
        "medium": "think hard",  # ~10,000 tokens
        "high": "ultrathink",  # ~31,999 tokens
    }

    def __init__(self, cli_path: str = "claude"):
        self.cli_path = cli_path
        self.settings = get_settings()

    def supports_streaming(self) -> bool:
        return True

    def supports_thinking(self) -> bool:
        return True  # Supported via keyword injection

    def _get_configured_models(self) -> list[str]:
        """Get models from settings or use defaults."""
        if self.settings.claude_models:
            return [m.strip() for m in self.settings.claude_models.split(",") if m.strip()]
        return self.DEFAULT_MODELS

    def get_models(self) -> list[str]:
        return self._get_configured_models()

    async def list_models(self) -> list[str]:
        return self._get_configured_models()

    def _get_thinking_keyword(self, thinking: dict[str, Any] | None) -> str | None:
        """
        Get thinking keyword based on configuration.

        Args:
            thinking: Thinking config with 'enabled' and 'budget_tokens'

        Returns:
            Thinking keyword to prepend to prompt, or None
        """
        if not thinking or not thinking.get("enabled"):
            return None

        budget = thinking.get("budget_tokens", 10000)

        # Map budget to keyword
        if budget >= 20000:
            return self.THINKING_KEYWORDS["high"]
        elif budget >= 8000:
            return self.THINKING_KEYWORDS["medium"]
        else:
            return self.THINKING_KEYWORDS["low"]

    def _extract_new_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Extract only new messages for resumed sessions.

        When resuming a CLI session, we only need to send messages since
        the last assistant response. The CLI maintains its own context.

        Args:
            messages: Full conversation history

        Returns:
            Only the new messages (after last assistant response)
        """
        if not messages:
            return messages

        # Find the last assistant message index
        last_assistant_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                last_assistant_idx = i
                break

        if last_assistant_idx == -1:
            # No assistant message found - send only the last user message
            # (system messages are handled separately)
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    return [messages[i]]
            return messages  # Fallback to all messages

        # Return messages after the last assistant response
        # These are typically tool results and new user messages
        new_messages = messages[last_assistant_idx + 1 :]

        if new_messages:
            return new_messages

        # If no new messages after assistant, this is unusual
        # Return the last user message before the assistant response
        for i in range(last_assistant_idx - 1, -1, -1):
            if messages[i].get("role") == "user":
                return [messages[i]]

        return messages  # Fallback

    def _format_messages(
        self,
        messages: list[dict[str, Any]],
        thinking: dict[str, Any] | None = None,
        resume_session: bool = False,
    ) -> tuple[str | None, str]:
        """
        Format messages into system prompt and user prompt.

        Args:
            messages: List of messages
            thinking: Thinking configuration
            resume_session: If True, only format new messages (CLI has context)

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        # When resuming, only include new messages - CLI has the context
        if resume_session:
            messages = self._extract_new_messages(messages)
            logger.debug(f"Resuming session: extracted {len(messages)} new message(s)")

        system_parts = []
        conversation_parts = []

        for msg in messages:
            role = msg.get("role", "user")
            raw_content = msg.get("content", "")
            content = extract_content(raw_content)

            if role == "system":
                # Skip system prompt when resuming - CLI already has it
                if not resume_session:
                    system_parts.append(content)
            elif role == "user":
                conversation_parts.append(f"User: {content}")
            elif role == "assistant":
                conversation_parts.append(f"Assistant: {content}")

        system_prompt = "\n\n".join(system_parts) if system_parts else None
        user_prompt = "\n\n".join(conversation_parts)

        # Inject thinking keyword if enabled
        thinking_keyword = self._get_thinking_keyword(thinking)
        if thinking_keyword:
            # Prepend thinking instruction
            user_prompt = f"[{thinking_keyword}]\n\n{user_prompt}"
            logger.debug(f"Injected thinking keyword: {thinking_keyword}")

        return system_prompt, user_prompt

    def _normalize_model(self, model: str) -> str:
        """Strip provider prefix from model name if present."""
        if model.startswith("claude:"):
            return model[7:]  # Remove "claude:" prefix
        return model

    def _build_command(
        self,
        model: str,
        system_prompt: str | None = None,
        system_prompt_file: str | None = None,
        stream: bool = False,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """Build CLI command with correct Claude Code parameters."""
        cmd = [self.cli_path]

        # Non-interactive print mode (required for scripting)
        cmd.append("-p")

        # Model selection - strip provider prefix if present
        # Claude Code accepts aliases like 'sonnet', 'opus' or full model names
        normalized_model = self._normalize_model(model)
        cmd.extend(["--model", normalized_model])

        # Session resumption for multi-turn conversations
        if session_id:
            cmd.extend(["--resume", session_id])

        # System prompt (if provided) - only on first message.
        # Large prompts go through --system-prompt-file to avoid the
        # MAX_ARG_STRLEN (~128 KiB per argv) kernel limit.
        if not session_id:
            if system_prompt_file:
                cmd.extend(["--system-prompt-file", system_prompt_file])
            elif system_prompt:
                cmd.extend(["--system-prompt", system_prompt])

        # Output format for streaming
        if stream:
            cmd.extend(["--output-format", "stream-json"])
            cmd.append("--verbose")  # Required for stream-json with -p
        else:
            cmd.extend(["--output-format", "json"])

        # Permission level settings
        permission_level = self.settings.claude_permission_level.lower()
        if permission_level == "chat":
            # Chat-only: NO local operations - pure LLM text completion
            # Disables all tools: no file access, no shell, no web - safe for Aider/clients
            cmd.extend(["--tools", ""])
        elif permission_level == "readonly":
            # Read-only: only allow read operations
            cmd.extend(["--tools", "Read,Glob,Grep,Task"])
        elif permission_level == "edit":
            # Edit: allow read + file modifications, no shell
            cmd.extend(["--tools", "Read,Glob,Grep,Edit,Write,NotebookEdit,Task"])
            cmd.extend(["--disallowedTools", "Bash,WebFetch,WebSearch"])
        else:  # full
            # Full: bypass all permission checks
            cmd.append("--dangerously-skip-permissions")

        # Note: prompt is passed via stdin to avoid command-line length limits

        return cmd

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str,
        stream: bool = False,
        thinking: dict[str, Any] | None = None,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
        """Generate completion using Claude Code CLI.

        Args:
            messages: List of messages
            model: Model name
            stream: Whether to stream the response
            thinking: Thinking configuration
            session_id: CLI session ID for multi-turn (from previous response)
            **kwargs: Additional arguments

        Returns:
            Response dict with 'content', 'thinking', and 'session_id' fields
        """
        # When resuming a session, CLI already has context - only send new messages
        resume_session = session_id is not None
        system_prompt, user_prompt = self._format_messages(
            messages, thinking, resume_session=resume_session
        )

        # Spill oversized system prompts into a temp file to dodge the exec
        # argv limit (MAX_ARG_STRLEN ~= 128 KiB). Attached context files +
        # long session prompts routinely cross this threshold.
        system_prompt_file: str | None = None
        if (
            system_prompt
            and not session_id
            and len(system_prompt.encode("utf-8")) > _SYSTEM_PROMPT_ARGV_LIMIT
        ):
            fd, system_prompt_file = tempfile.mkstemp(prefix="claude-sp-", suffix=".txt")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(system_prompt)
            except Exception:
                Path(system_prompt_file).unlink(missing_ok=True)
                raise
            logger.debug(f"System prompt {len(system_prompt)} chars -> {system_prompt_file}")

        cmd = self._build_command(
            model=model,
            system_prompt=None if system_prompt_file else system_prompt,
            system_prompt_file=system_prompt_file,
            stream=stream,
            session_id=session_id,
            **kwargs,
        )

        logger.debug(
            f"Running command: {' '.join(cmd)} (prompt via stdin, {len(user_prompt)} chars)"
        )

        if stream:
            return self._stream_complete(cmd, model, user_prompt, system_prompt_file)
        else:
            try:
                return await self._sync_complete(cmd, model, user_prompt)
            finally:
                if system_prompt_file:
                    Path(system_prompt_file).unlink(missing_ok=True)

    async def _sync_complete(
        self,
        cmd: list[str],
        model: str,
        prompt: str,
    ) -> dict[str, Any]:
        """Non-streaming completion."""
        try:
            cli_kwargs: dict[str, Any] = dict(
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_build_cli_env(),
            )
            cli_cwd = _cli_cwd()
            if cli_cwd:
                cli_kwargs["cwd"] = cli_cwd
            process = await create_subprocess(cmd, **cli_kwargs)

            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt.encode()),
                timeout=self.settings.cli_timeout,
            )

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Claude CLI error: {error_msg}")
                raise RuntimeError(f"Claude CLI failed: {error_msg}")

            output = stdout.decode().strip()

            # Parse JSON output
            try:
                data = json.loads(output)

                # Extract response content
                content = data.get("result", output)

                # Extract session ID for multi-turn
                session_id = data.get("session_id")

                # Extract cost and usage data
                cost_usd = data.get("total_cost_usd", 0)
                usage = data.get("usage", {})

                return {
                    "content": content,
                    "thinking": None,  # Claude doesn't expose thinking content
                    "session_id": session_id,
                    "cost_usd": cost_usd,
                    "usage": {
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
                        "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
                    },
                }
            except json.JSONDecodeError:
                # Fallback to raw text
                return {
                    "content": output,
                    "thinking": None,
                    "session_id": None,
                    "cost_usd": 0,
                    "usage": {},
                }

        except asyncio.TimeoutError:
            logger.error("Claude CLI timeout")
            raise

    async def _stream_complete(
        self,
        cmd: list[str],
        model: str,
        prompt: str,
        cleanup_file: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming completion using stream-json format."""
        try:
            cli_kwargs: dict[str, Any] = dict(
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_build_cli_env(),
            )
            cli_cwd = _cli_cwd()
            if cli_cwd:
                cli_kwargs["cwd"] = cli_cwd
            process = await create_subprocess(cmd, **cli_kwargs)

            # Write prompt to stdin and close it
            process.stdin.write(prompt.encode())
            await process.stdin.drain()
            process.stdin.close()
            await process.stdin.wait_closed()

            buffer = ""
            decoder = codecs.getincrementaldecoder("utf-8")("replace")

            while True:
                chunk = await asyncio.wait_for(
                    process.stdout.read(1024),
                    timeout=self.settings.stream_timeout,
                )

                if not chunk:
                    # Flush any remaining bytes
                    buffer += decoder.decode(b"", final=True)
                    break

                buffer += decoder.decode(chunk)

                # Parse JSON lines from stream-json format
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        msg_type = data.get("type")
                        content = None

                        # Parse different message types in stream-json format
                        # Only use "assistant" messages - "result" is a duplicate
                        if msg_type == "assistant":
                            # Extract text from message content array
                            message = data.get("message", {})
                            content_parts = message.get("content", [])
                            for part in content_parts:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    content = part.get("text", "")
                                    break
                        # Skip "result" type - it duplicates "assistant" content

                        if content:
                            yield {
                                "content": content,
                                "thinking": None,
                                "done": False,
                            }
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        logger.debug(f"Skipping non-JSON line: {line[:50]}")

            # Final chunk
            yield {
                "content": None,
                "thinking": None,
                "done": True,
            }

            await process.wait()

        except asyncio.TimeoutError:
            logger.error("Claude CLI stream timeout")
            raise
        finally:
            if cleanup_file:
                Path(cleanup_file).unlink(missing_ok=True)
