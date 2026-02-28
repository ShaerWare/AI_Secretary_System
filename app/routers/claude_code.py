"""
Claude Code Web UI — WebSocket endpoint + REST session management.

WebSocket /admin/claude-code/ws?token=<jwt>
  Client → Server: {action: "start"|"message"|"abort", prompt?, session_id?}
  Server → Client: {type: "session_init"|"text_delta"|"thinking_delta"|
                     "tool_use_start"|"tool_use_input"|"tool_result"|
                     "turn_complete"|"done"|"error"|"aborted"}

REST (admin-only):
  GET    /admin/claude-code/sessions      — list sessions
  GET    /admin/claude-code/sessions/{id} — session detail
  DELETE /admin/claude-code/sessions/{id} — delete session
"""

import asyncio
import codecs
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, WebSocket, WebSocketDisconnect

from auth_manager import TokenPayload, decode_token, require_permission, workspace_context


router = APIRouter(prefix="/admin/claude-code", tags=["claude-code"])
logger = logging.getLogger(__name__)

CLAUDE_CLI = shutil.which("claude") or "/usr/local/bin/claude"
_ALLOWED_USERS = {"shaerware", "ivan"}
_ALLOWED_CWDS = ["/opt/ai-secretary", "/root", "/tmp"]
_DEFAULT_CWD = "/opt/ai-secretary"

# One active WS per user
_active_connections: dict[int, WebSocket] = {}
# Track running subprocess per user for abort
_active_processes: dict[int, asyncio.subprocess.Process] = {}
# Track temp context dirs per user for cleanup
_context_dirs: dict[int, str] = {}


def _ws_auth(token: str) -> TokenPayload:
    """Authenticate WebSocket via query param token."""
    payload = decode_token(token)
    if payload is None:
        raise ValueError("Invalid or expired token")
    if payload.sub not in _ALLOWED_USERS:
        raise ValueError("Access denied")
    return payload


async def _send(ws: WebSocket, msg: dict) -> None:
    """Send JSON to WebSocket, ignore if already closed."""
    try:
        await ws.send_json(msg)
    except Exception as exc:
        logger.debug("WS send failed (%s): %s", msg.get("type", "?"), exc)


def _prepare_context_files(
    user_id: int, context_files: list[dict[str, str]]
) -> tuple[str, list[str]]:
    """Write context files to temp dir, return (dir_path, file_paths)."""
    # Clean up previous context dir
    old_dir = _context_dirs.pop(user_id, None)
    if old_dir and Path(old_dir).is_dir():
        shutil.rmtree(old_dir, ignore_errors=True)

    tmp_dir = tempfile.mkdtemp(prefix=f"cc-ctx-{user_id}-")
    _context_dirs[user_id] = tmp_dir
    paths = []
    for f in context_files:
        name = f.get("name", "file.txt").replace("/", "_").replace("..", "_")
        content = f.get("content", "")
        fpath = str(Path(tmp_dir) / name)
        with open(fpath, "w", encoding="utf-8") as fh:
            fh.write(content)
        paths.append(fpath)
    return tmp_dir, paths


def _validate_cwd(cwd: Optional[str]) -> str:
    """Validate and return working directory."""
    if not cwd:
        return _DEFAULT_CWD
    cwd = cwd.rstrip("/")
    if cwd in _ALLOWED_CWDS or any(cwd.startswith(d + "/") for d in _ALLOWED_CWDS):
        if Path(cwd).is_dir():
            return cwd
    return _DEFAULT_CWD


async def _resolve_project(project_id: Optional[int], owner_id: int) -> Optional[dict]:
    """Look up a CC project by ID. Returns project dict or None."""
    if not project_id:
        return None
    from db.integration import async_claude_code_project_manager

    projects = await async_claude_code_project_manager.list_projects(owner_id=owner_id)
    for p in projects:
        if p["id"] == project_id:
            return p
    return None


async def _run_claude(
    ws: WebSocket,
    user_id: int,
    prompt: str,
    session_id: Optional[str],
    db_session_id: str,
    cwd: Optional[str] = None,
    context_files: Optional[list[dict[str, str]]] = None,
    project: Optional[dict] = None,
) -> Optional[str]:
    """
    Spawn claude CLI subprocess, parse NDJSON stream, relay events over WS.
    Returns the CLI session_id (for resume).

    If *project* is an SSH project, wraps the claude command in an SSH call.
    """
    from db.integration import async_claude_code_manager

    is_ssh = project and project.get("type") == "ssh"

    if is_ssh:
        working_dir = _DEFAULT_CWD  # local cwd for the ssh subprocess
    elif project:
        working_dir = _validate_cwd(project.get("path"))
    else:
        working_dir = _validate_cwd(cwd)

    # Build the base claude command parts
    claude_args = [
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        "50",
        "--permission-mode",
        "acceptEdits",
    ]

    if session_id:
        claude_args.extend(["--resume", session_id])

    # Write context files and add paths to prompt (local mode only)
    file_paths: list[str] = []
    if context_files and not is_ssh:
        ctx_dir, file_paths = _prepare_context_files(user_id, context_files)
        claude_args.extend(["--add-dir", ctx_dir])

    # Allow access to additional directories if cwd is not /root (local mode only)
    if not is_ssh and working_dir != "/root":
        claude_args.extend(["--add-dir", working_dir])

    env = dict(os.environ)
    env.pop("CLAUDECODE", None)  # prevent nested-session guard

    # Prepend context files info to prompt
    if file_paths:
        files_section = "Context files from chat:\n"
        for fp in file_paths:
            files_section += f"  - {fp}\n"
        files_section += "\nPlease read these files first, then proceed with the task.\n\n"
        prompt = files_section + prompt

    if is_ssh:
        # SSH mode: run claude on remote host
        ssh_host = project["ssh_host"]
        ssh_user = project.get("ssh_user", "root")
        ssh_port = project.get("ssh_port", 22)
        ssh_key_path = project.get("ssh_key_path")
        remote_path = project.get("path", "/root")

        # Build the remote claude command string
        remote_claude_cmd = "claude " + " ".join(claude_args)
        # Wrap in cd + exec on remote
        remote_full = f"cd {remote_path} && {remote_claude_cmd}"

        ssh_cmd: list[str] = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "BatchMode=yes",
            "-p",
            str(ssh_port),
        ]
        if ssh_key_path:
            ssh_cmd.extend(["-i", ssh_key_path])
        ssh_cmd.append(f"{ssh_user}@{ssh_host}")
        ssh_cmd.append(remote_full)

        cmd = ssh_cmd
    else:
        cmd = [CLAUDE_CLI] + claude_args

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=working_dir,
    )

    _active_processes[user_id] = process

    # Write prompt to stdin
    process.stdin.write(prompt.encode())
    await process.stdin.drain()
    process.stdin.close()
    await process.stdin.wait_closed()

    cli_session_id: Optional[str] = session_id
    model: Optional[str] = None
    total_turns = 0

    buffer = ""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")

    try:
        while True:
            try:
                chunk = await asyncio.wait_for(
                    process.stdout.read(4096),
                    timeout=300,  # 5 min max silence
                )
            except asyncio.TimeoutError:
                await _send(ws, {"type": "error", "error": "CLI timeout (5 min)"})
                break

            if not chunk:
                buffer += decoder.decode(b"", final=True)
                # Process any remaining lines
                if buffer.strip():
                    remaining = await _parse_and_relay(ws, buffer.strip())
                    if remaining:
                        if remaining.get("cli_session_id"):
                            cli_session_id = remaining["cli_session_id"]
                        if remaining.get("model"):
                            model = remaining["model"]
                        if remaining.get("turn"):
                            total_turns += 1
                break

            buffer += decoder.decode(chunk)

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                result = await _parse_and_relay(ws, line)
                if result:
                    if result.get("cli_session_id"):
                        cli_session_id = result["cli_session_id"]
                    if result.get("model"):
                        model = result["model"]
                    if result.get("turn"):
                        total_turns += 1

    except asyncio.CancelledError:
        # Abort requested
        process.kill()
        await process.wait()
        await _send(ws, {"type": "aborted"})
        await async_claude_code_manager.update_session(db_session_id, status="aborted")
        return cli_session_id
    finally:
        _active_processes.pop(user_id, None)

    await process.wait()

    # Read stderr for diagnostics
    stderr_data = b""
    try:
        stderr_data = await asyncio.wait_for(process.stderr.read(), timeout=2)
    except Exception:
        pass
    stderr_text = stderr_data.decode(errors="replace")[:500] if stderr_data else ""
    if stderr_text:
        logger.warning("Claude CLI stderr: %s", stderr_text)

    exit_code = process.returncode
    final_status = "completed" if exit_code == 0 else "error"

    # If process failed, notify the client (it may not have received a result event)
    if exit_code != 0:
        err_msg = stderr_text.strip() or f"Claude CLI exited with code {exit_code}"
        await _send(ws, {"type": "error", "error": err_msg})
        await _send(
            ws,
            {
                "type": "done",
                "session_id": cli_session_id,
                "cost_usd": None,
                "duration_ms": None,
                "result": "",
            },
        )

    await async_claude_code_manager.update_session(
        db_session_id,
        cli_session_id=cli_session_id,
        model=model,
        total_turns=total_turns,
        status=final_status,
    )

    return cli_session_id


async def _parse_and_relay(ws: WebSocket, line: str) -> Optional[dict[str, Any]]:
    """Parse a single NDJSON line and relay as WebSocket event. Returns metadata."""
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        logger.debug("Skipping non-JSON line: %s", line[:80])
        return None

    msg_type = data.get("type")
    result: dict[str, Any] = {}

    if msg_type == "system":
        # Init event — extract session_id and model
        cli_sid = data.get("session_id")
        mdl = data.get("model")
        if cli_sid:
            result["cli_session_id"] = cli_sid
        if mdl:
            result["model"] = mdl
        await _send(
            ws,
            {
                "type": "session_init",
                "session_id": cli_sid,
                "model": mdl,
                "tools": data.get("tools", []),
                "mcp_servers": data.get("mcp_servers", []),
            },
        )

    elif msg_type == "assistant":
        # Full assistant message — extract tool_use blocks
        message = data.get("message", {})
        content_parts = message.get("content", [])
        for part in content_parts:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_use":
                await _send(
                    ws,
                    {
                        "type": "tool_use_input",
                        "tool_use_id": part.get("id"),
                        "name": part.get("name"),
                        "input": part.get("input"),
                    },
                )
            elif part.get("type") == "text" and part.get("text"):
                # Non-streaming fallback: emit as text_delta
                await _send(
                    ws,
                    {
                        "type": "text_delta",
                        "text": part["text"],
                    },
                )
            elif part.get("type") == "thinking" and part.get("thinking"):
                await _send(
                    ws,
                    {
                        "type": "thinking_delta",
                        "text": part["thinking"],
                    },
                )

    elif msg_type == "user":
        # User message with tool_result
        message = data.get("message", {})
        content_parts = message.get("content", [])
        for part in content_parts:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_result":
                await _send(
                    ws,
                    {
                        "type": "tool_result",
                        "tool_use_id": part.get("tool_use_id"),
                        "content": _extract_tool_result_text(part.get("content")),
                        "is_error": part.get("is_error", False),
                    },
                )
        result["turn"] = True

    elif msg_type == "content_block_start":
        cb = data.get("content_block", {})
        if cb.get("type") == "tool_use":
            await _send(
                ws,
                {
                    "type": "tool_use_start",
                    "tool_use_id": cb.get("id"),
                    "name": cb.get("name"),
                },
            )

    elif msg_type == "content_block_delta":
        delta = data.get("delta", {})
        delta_type = delta.get("type")
        if delta_type == "text_delta":
            await _send(
                ws,
                {
                    "type": "text_delta",
                    "text": delta.get("text", ""),
                },
            )
        elif delta_type == "thinking_delta":
            await _send(
                ws,
                {
                    "type": "thinking_delta",
                    "text": delta.get("thinking", ""),
                },
            )
        elif delta_type == "input_json_delta":
            await _send(
                ws,
                {
                    "type": "tool_use_input_delta",
                    "partial_json": delta.get("partial_json", ""),
                },
            )

    elif msg_type == "result":
        # Final result
        cost = data.get("cost_usd")
        duration = data.get("duration_ms")
        session_id = data.get("session_id")
        if session_id:
            result["cli_session_id"] = session_id
        await _send(
            ws,
            {
                "type": "done",
                "session_id": session_id,
                "cost_usd": cost,
                "duration_ms": duration,
                "result": _extract_result_text(data),
            },
        )

    return result if result else None


def _extract_tool_result_text(content: Any) -> str:
    """Extract text from tool_result content (may be string or list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content) if content else ""


def _extract_result_text(data: dict) -> str:
    """Extract final text from result event."""
    result = data.get("result", "")
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result.get("text", "")
    return ""


# ============== WebSocket Endpoint ==============


@router.websocket("/ws")
async def claude_code_ws(websocket: WebSocket, token: str = ""):
    """WebSocket endpoint for Claude Code CLI interaction."""
    # Auth
    try:
        payload = _ws_auth(token)
    except ValueError as e:
        await websocket.close(code=4003, reason=str(e))
        return

    user_id = payload.user_id

    # Only one connection per user
    if user_id in _active_connections:
        old_ws = _active_connections[user_id]
        try:
            await old_ws.close(code=4001, reason="Replaced by new connection")
        except Exception:
            pass

    await websocket.accept()
    _active_connections[user_id] = websocket
    logger.info("Claude Code WS connected: user=%s", payload.sub)

    try:
        while True:
            raw = await websocket.receive_json()
            action = raw.get("action")

            if action == "start":
                await _handle_start(websocket, user_id, raw, payload.workspace_id)
            elif action == "message":
                await _handle_message(websocket, user_id, raw, payload.workspace_id)
            elif action == "abort":
                await _handle_abort(user_id)
            else:
                await _send(websocket, {"type": "error", "error": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        logger.info("Claude Code WS disconnected: user=%s", payload.sub)
    except Exception as e:
        logger.exception("Claude Code WS error: %s", e)
        await _send(websocket, {"type": "error", "error": str(e)})
    finally:
        _active_connections.pop(user_id, None)
        # Kill any running process
        proc = _active_processes.pop(user_id, None)
        if proc and proc.returncode is None:
            proc.kill()
        # Clean up context files
        ctx_dir = _context_dirs.pop(user_id, None)
        if ctx_dir and Path(ctx_dir).is_dir():
            shutil.rmtree(ctx_dir, ignore_errors=True)


async def _handle_start(ws: WebSocket, user_id: int, raw: dict, workspace_id: int = 1) -> None:
    """Handle 'start' action — new session."""
    from db.integration import async_claude_code_manager

    prompt = raw.get("prompt", "").strip()
    if not prompt:
        await _send(ws, {"type": "error", "error": "prompt is required"})
        return

    # Check no process already running
    if user_id in _active_processes:
        await _send(ws, {"type": "error", "error": "A process is already running"})
        return

    cwd = raw.get("cwd")
    context_files = raw.get("context_files")
    project_id = raw.get("project_id")

    # Resolve project from DB if provided
    project = await _resolve_project(project_id, user_id) if project_id else None

    # Create DB session
    title = prompt[:50]
    db_session = await async_claude_code_manager.create_session(
        title=title, owner_id=user_id, workspace_id=workspace_id
    )

    await _send(ws, {"type": "session_created", "session": db_session})

    cli_session_id = await _run_claude(
        ws,
        user_id,
        prompt,
        session_id=None,
        db_session_id=db_session["id"],
        cwd=cwd,
        context_files=context_files,
        project=project,
    )

    if cli_session_id:
        await async_claude_code_manager.update_session(
            db_session["id"], cli_session_id=cli_session_id
        )


async def _handle_message(ws: WebSocket, user_id: int, raw: dict, workspace_id: int = 1) -> None:
    """Handle 'message' action — continue existing session."""
    from db.integration import async_claude_code_manager

    prompt = raw.get("prompt", "").strip()
    session_id = raw.get("session_id", "").strip()
    cli_session_id = raw.get("cli_session_id", "").strip()

    if not prompt:
        await _send(ws, {"type": "error", "error": "prompt is required"})
        return

    if not cli_session_id and not session_id:
        await _send(ws, {"type": "error", "error": "session_id or cli_session_id required"})
        return

    if user_id in _active_processes:
        await _send(ws, {"type": "error", "error": "A process is already running"})
        return

    # Look up DB session for the cli_session_id
    db_session_id = session_id
    if not db_session_id and cli_session_id:
        # Create a follow-up entry
        db_session = await async_claude_code_manager.create_session(
            title=prompt[:50], owner_id=user_id, workspace_id=workspace_id
        )
        db_session_id = db_session["id"]
        await async_claude_code_manager.update_session(db_session_id, cli_session_id=cli_session_id)

    # Update the session status
    await async_claude_code_manager.update_session(db_session_id, status="active")

    result_cli_id = await _run_claude(
        ws,
        user_id,
        prompt,
        session_id=cli_session_id or None,
        db_session_id=db_session_id,
    )

    if result_cli_id and db_session_id:
        await async_claude_code_manager.update_session(db_session_id, cli_session_id=result_cli_id)


async def _handle_abort(user_id: int) -> None:
    """Abort the running Claude process."""
    proc = _active_processes.get(user_id)
    if proc and proc.returncode is None:
        proc.kill()
        logger.info("Claude Code process killed for user=%d", user_id)


# ============== REST Endpoints ==============


@router.get("/sessions")
async def list_sessions(user=Depends(require_permission("claude_code", "manage"))):
    """List Claude Code sessions."""
    from db.integration import async_claude_code_manager

    _owner_id, ws_id = workspace_context(user, "claude_code")
    sessions = await async_claude_code_manager.list_sessions(owner_id=user.id, workspace_id=ws_id)
    return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user=Depends(require_permission("claude_code", "manage"))):
    """Get a specific Claude Code session."""
    from db.integration import async_claude_code_manager

    _owner_id, ws_id = workspace_context(user, "claude_code")
    session = await async_claude_code_manager.get_session(session_id, workspace_id=ws_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str, user=Depends(require_permission("claude_code", "manage"))
):
    """Delete a Claude Code session."""
    from db.integration import async_claude_code_manager

    _owner_id, ws_id = workspace_context(user, "claude_code")
    deleted = await async_claude_code_manager.delete_session(session_id, workspace_id=ws_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


@router.get("/directories")
async def list_directories(user=Depends(require_permission("claude_code", "manage"))):
    """List allowed working directories for Claude Code."""
    return {"directories": _ALLOWED_CWDS, "default": _DEFAULT_CWD}


# ============== Project CRUD ==============


@router.get("/projects")
async def list_projects(user=Depends(require_permission("claude_code", "manage"))):
    """List Claude Code projects (DB + built-in defaults)."""
    from db.integration import async_claude_code_project_manager

    _owner_id, ws_id = workspace_context(user, "claude_code")
    db_projects = await async_claude_code_project_manager.list_projects(
        owner_id=user.id, workspace_id=ws_id
    )

    # Prepend built-in defaults so they always show
    builtins = [
        {"id": None, "name": d, "path": d, "type": "local", "builtin": True} for d in _ALLOWED_CWDS
    ]
    return {"projects": builtins + db_projects}


@router.post("/projects")
async def create_project(
    body: dict = Body(...),
    user=Depends(require_permission("claude_code", "manage")),
):
    """Create a new Claude Code project."""
    from db.integration import async_claude_code_project_manager

    name = (body.get("name") or "").strip()
    path = (body.get("path") or "").strip()
    ptype = body.get("type", "local")
    if not name or not path:
        raise HTTPException(status_code=400, detail="name and path are required")
    if ptype not in ("local", "ssh"):
        raise HTTPException(status_code=400, detail="type must be 'local' or 'ssh'")
    if ptype == "ssh" and not body.get("ssh_host"):
        raise HTTPException(status_code=400, detail="ssh_host is required for SSH projects")

    _owner_id, ws_id = workspace_context(user, "claude_code")
    project = await async_claude_code_project_manager.create_project(
        name=name,
        path=path,
        owner_id=user.id,
        type=ptype,
        ssh_host=body.get("ssh_host"),
        ssh_user=body.get("ssh_user", "root"),
        ssh_port=int(body.get("ssh_port", 22)),
        ssh_key_path=body.get("ssh_key_path"),
        workspace_id=ws_id,
    )
    return {"project": project}


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int,
    user=Depends(require_permission("claude_code", "manage")),
):
    """Delete a Claude Code project."""
    from db.integration import async_claude_code_project_manager

    _owner_id, ws_id = workspace_context(user, "claude_code")
    deleted = await async_claude_code_project_manager.delete_project(
        project_id, owner_id=user.id, workspace_id=ws_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted"}
