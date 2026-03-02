"""GitHub Repository Sync Service — clones repos and converts files to markdown for RAG.

Pure functions: no DB access. Handles git clone/pull, file filtering, and markdown conversion.
"""

import fnmatch
import logging
import os
import shutil
import subprocess
from pathlib import Path


logger = logging.getLogger(__name__)

GITHUB_REPOS_DIR = Path("data/github-repos")
MAX_FILE_SIZE = 100_000  # 100KB

# Binary extensions to always skip
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".webp",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".obj",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".mkv",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".DS_Store",
}

# Language map for code fences
LANG_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".vue": "vue",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".xml": "xml",
    ".dockerfile": "dockerfile",
    ".tf": "hcl",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".md": "markdown",
    ".rst": "rst",
    ".txt": "text",
}


def _clean_env() -> dict[str, str]:
    """Return os.environ copy with proxy vars stripped (xray proxy breaks git)."""
    env = os.environ.copy()
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        env.pop(key, None)
    return env


def get_repo_dir(owner: str, repo: str) -> Path:
    """Get the local directory for a cloned repo."""
    return GITHUB_REPOS_DIR / f"{owner}-{repo}"


def get_rag_dir(owner: str, repo: str) -> Path:
    """Get the RAG output directory for a repo."""
    return get_repo_dir(owner, repo) / "_rag"


def _build_clone_url(owner: str, repo: str, token: str | None = None) -> str:
    """Build GitHub clone URL, with token for private repos."""
    if token:
        return f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    return f"https://github.com/{owner}/{repo}.git"


def clone_repo(
    owner: str,
    repo: str,
    branch: str = "main",
    token: str | None = None,
) -> str:
    """Clone a GitHub repo (shallow). Returns HEAD commit SHA.

    Raises subprocess.CalledProcessError on failure.
    """
    target = get_repo_dir(owner, repo)
    if target.exists():
        shutil.rmtree(target)

    target.mkdir(parents=True, exist_ok=True)
    url = _build_clone_url(owner, repo, token)

    cmd = ["git", "clone", "--depth", "1", "--branch", branch, url, str(target)]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        env=_clean_env(),
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        # Sanitize token from error messages
        if token and token in stderr:
            stderr = stderr.replace(token, "***")
        raise subprocess.CalledProcessError(
            result.returncode, "git clone", output=result.stdout, stderr=stderr
        )

    return get_head_sha(target)


def pull_repo(
    owner: str,
    repo: str,
    token: str | None = None,
) -> str:
    """Pull latest changes. Returns new HEAD commit SHA.

    For shallow clones, uses fetch + reset instead of pull.
    Raises subprocess.CalledProcessError on failure.
    """
    target = get_repo_dir(owner, repo)
    if not target.exists():
        raise FileNotFoundError(f"Repo directory not found: {target}")

    # For shallow clones, fetch --depth 1 and reset
    url = _build_clone_url(owner, repo, token)
    fetch_cmd = ["git", "-C", str(target), "fetch", "--depth", "1", url]
    result = subprocess.run(
        fetch_cmd,
        capture_output=True,
        text=True,
        timeout=300,
        env=_clean_env(),
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if token and token in stderr:
            stderr = stderr.replace(token, "***")
        raise subprocess.CalledProcessError(
            result.returncode, "git fetch", output=result.stdout, stderr=stderr
        )

    # Reset to FETCH_HEAD
    reset_cmd = ["git", "-C", str(target), "reset", "--hard", "FETCH_HEAD"]
    subprocess.run(reset_cmd, capture_output=True, text=True, timeout=60, env=_clean_env())

    return get_head_sha(target)


def get_head_sha(repo_dir: Path) -> str:
    """Get HEAD commit SHA from a local repo."""
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


def should_include_file(
    filepath: Path,
    repo_root: Path,
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> bool:
    """Check if a file should be included based on patterns."""
    rel_path = str(filepath.relative_to(repo_root))
    filename = filepath.name
    suffix = filepath.suffix.lower()

    # Always skip binary files
    if suffix in BINARY_EXTENSIONS:
        return False

    # Always skip _rag directory
    if "_rag" in rel_path.split("/"):
        return False

    # Check exclude patterns (match against filename and any path component)
    for pattern in exclude_patterns:
        # Pattern matches filename
        if fnmatch.fnmatch(filename, pattern):
            return False
        # Pattern matches any directory component
        for part in rel_path.split("/"):
            if fnmatch.fnmatch(part, pattern):
                return False

    # Check include patterns (match against filename)
    return any(fnmatch.fnmatch(filename, pattern) for pattern in include_patterns)


def convert_file_to_markdown(filepath: Path, repo_root: Path) -> tuple[str, str]:
    """Convert a file to markdown format. Returns (title, content).

    - .md files: returned as-is with title from first heading
    - Code files: wrapped in code fence with file path as title
    """
    rel_path = str(filepath.relative_to(repo_root))
    suffix = filepath.suffix.lower()

    try:
        raw = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return f"File: {rel_path}", f"# File: {rel_path}\n\n*Error reading file*\n"

    if suffix == ".md":
        # Extract title from first heading
        title = rel_path
        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break
        return title, raw

    # Code file — wrap in fence
    lang = LANG_MAP.get(suffix, "")
    title = f"File: {rel_path}"
    content = f"# {title}\n\n```{lang}\n{raw}\n```\n"
    return title, content


def build_repo_documents(
    owner: str,
    repo: str,
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> list[tuple[str, str, str, int]]:
    """Scan repo and convert files to markdown.

    Returns list of (filename, title, content, file_size) tuples.
    """
    repo_dir = get_repo_dir(owner, repo)
    if not repo_dir.exists():
        return []

    documents: list[tuple[str, str, str, int]] = []

    for filepath in sorted(repo_dir.rglob("*")):
        if not filepath.is_file():
            continue

        # Skip files over size limit
        try:
            file_size = filepath.stat().st_size
        except OSError:
            continue
        if file_size > MAX_FILE_SIZE:
            continue

        if not should_include_file(filepath, repo_dir, include_patterns, exclude_patterns):
            continue

        title, content = convert_file_to_markdown(filepath, repo_dir)
        rel_path = filepath.relative_to(repo_dir)
        # Sanitize filename for RAG: prefix with owner-repo, replace / with --
        safe_name = f"{owner}-{repo}--{str(rel_path).replace('/', '--')}"
        if not safe_name.endswith(".md"):
            safe_name += ".md"

        documents.append((safe_name, title, content, file_size))

    return documents


def write_rag_documents(
    owner: str,
    repo: str,
    documents: list[tuple[str, str, str, int]],
) -> int:
    """Write RAG markdown files to the _rag directory.

    Returns total size in bytes of written files.
    """
    rag_dir = get_rag_dir(owner, repo)

    # Clean old RAG files
    if rag_dir.exists():
        shutil.rmtree(rag_dir)
    rag_dir.mkdir(parents=True, exist_ok=True)

    total_size = 0
    for filename, _title, content, _file_size in documents:
        out_path = rag_dir / filename
        out_path.write_text(content, encoding="utf-8")
        total_size += len(content.encode("utf-8"))

    return total_size


def build_repo_summary(
    owner: str,
    repo: str,
    branch: str,
    file_count: int,
    total_size: int,
) -> str:
    """Build a summary document for the repo."""
    size_kb = total_size / 1024
    return (
        f"# GitHub Repository: {owner}/{repo}\n\n"
        f"- **Repository**: https://github.com/{owner}/{repo}\n"
        f"- **Branch**: {branch}\n"
        f"- **Indexed files**: {file_count}\n"
        f"- **Total size**: {size_kb:.1f} KB\n"
    )


def clean_repo_files(owner: str, repo: str) -> None:
    """Remove all local files for a repo (clone + RAG)."""
    repo_dir = get_repo_dir(owner, repo)
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
