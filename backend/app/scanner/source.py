"""Source-file lookup helper used by both scanners to extract snippet text.

Scanner outputs aren't a reliable source-of-truth for the matched source code:
Semgrep's ``extra.lines`` sometimes carries rule metadata rather than the raw
source; the LLM reviewer has no snippet at all and may report ``file_path`` with
inconsistent prefixing. This helper always goes back to the real file on disk
and extracts the requested line range, with tolerant path resolution.
"""

import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".next", "dist", "build"}
_MAX_WINDOW_LINES = 40


def _index_repo(repo_path: Path) -> dict[str, Path]:
    """Build ``{relative_posix_path: absolute_path}`` for every file in the repo."""
    index: dict[str, Path] = {}
    try:
        for path in repo_path.rglob("*"):
            if not path.is_file():
                continue
            if any(skip in path.parts for skip in _SKIP_DIRS):
                continue
            try:
                rel = path.relative_to(repo_path).as_posix()
            except ValueError:
                continue
            index[rel] = path
    except OSError as exc:
        log.warning("Failed to walk repo %s: %s", repo_path, exc)
    return index


@lru_cache(maxsize=32)
def _cached_index(repo_path_str: str) -> tuple[tuple[str, str], ...]:
    """LRU-cached wrapper around :func:`_index_repo`.

    Keyed by the stringified path and returned as a hashable tuple of
    ``(relative, absolute)`` pairs so ``lru_cache`` is happy.
    """
    repo_path = Path(repo_path_str)
    return tuple((rel, str(p)) for rel, p in _index_repo(repo_path).items())


def _resolve_file(repo_path: Path, file_path: str) -> Path | None:
    """Try several strategies to locate *file_path* inside *repo_path*."""
    if not file_path:
        return None

    normalized = file_path.replace("\\", "/").lstrip("./").lstrip("/")

    index_pairs = _cached_index(str(repo_path))
    index = {rel: Path(abs_) for rel, abs_ in index_pairs}

    # 1. Exact match.
    if normalized in index:
        return index[normalized]

    # 2. Suffix match — e.g. requested "demo-repos/x/server.js" but indexed as
    # "server.js". Prefer the longest match so we don't pick a same-named file
    # from a deeper directory by accident.
    suffix_candidates = [rel for rel in index if normalized.endswith(rel) or rel.endswith(normalized)]
    if suffix_candidates:
        best = max(suffix_candidates, key=len)
        return index[best]

    # 3. Basename fallback — last resort, only if exactly one file matches.
    basename = normalized.rsplit("/", 1)[-1]
    basename_candidates = [rel for rel in index if rel.rsplit("/", 1)[-1] == basename]
    if len(basename_candidates) == 1:
        return index[basename_candidates[0]]

    return None


def read_source_lines(
    repo_path: Path,
    file_path: str,
    start_line: int,
    end_line: int,
    context: int = 1,
) -> str:
    """Return real source text around ``(start_line, end_line)`` from the repo.

    Path resolution is tolerant: exact match, then suffix match, then
    unambiguous basename match. The returned window is padded by ``context``
    lines on each side and capped at :data:`_MAX_WINDOW_LINES` so a
    wildly-wrong LLM range can't dump the whole file.

    Returns ``""`` on any failure (file not found, unreadable, invalid range).
    """
    if repo_path is None or not file_path:
        return ""

    resolved = _resolve_file(repo_path, file_path)
    if resolved is None:
        return ""

    try:
        text = resolved.read_text(errors="replace")
    except OSError as exc:
        log.debug("Could not read %s: %s", resolved, exc)
        return ""

    lines = text.splitlines()
    total = len(lines)
    if total == 0:
        return ""

    s = start_line if start_line and start_line > 0 else 1
    e = end_line if end_line and end_line >= s else s

    window_start = max(1, s - context)
    window_end = min(total, e + context)

    if window_end - window_start + 1 > _MAX_WINDOW_LINES:
        window_end = window_start + _MAX_WINDOW_LINES - 1

    if window_start > total:
        return ""

    return "\n".join(lines[window_start - 1 : window_end])
