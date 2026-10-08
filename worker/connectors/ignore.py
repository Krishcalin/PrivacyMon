"""Ignore rules for the Git connector (SRS FR-2.1): a platform-level list of
directories and binary/vendored files that are never scanned, plus a pragmatic
subset of a repository's own ``.gitignore``.

This is deliberately NOT a full gitignore engine (no ``pathspec`` dependency in the
offline wheelhouse). It honours the forms that matter for excluding noise — directory
names, ``*.ext`` globs, trailing-slash directory rules and root-anchored paths — and
errs toward scanning (an unrecognised pattern is skipped, never applied too broadly),
so the worst case is a little extra work, never a silently skipped source file.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import PurePosixPath

# Directories that are build output, dependencies or VCS metadata — never source.
DEFAULT_IGNORE_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor",
    "dist", "build", "out", "target", "bin", "obj", ".next", ".nuxt",
    ".venv", "venv", "env", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode", ".gradle", "coverage", ".tox", "site-packages",
})

# Extensions that are not text source (so never carry parseable identifiers/literals).
BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".pdf", ".zip", ".gz", ".tar", ".tgz", ".7z", ".rar", ".jar", ".war",
    ".class", ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".mov", ".avi",
    ".lock", ".min.js", ".map",
})


class IgnoreRules:
    """Platform ignore list plus an optional ``.gitignore`` pattern subset."""

    def __init__(self, gitignore_patterns: list[str] | None = None,
                 ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS,
                 binary_extensions: frozenset[str] = BINARY_EXTENSIONS):
        self.ignore_dirs = ignore_dirs
        self.binary_extensions = binary_extensions
        self.gitignore = [p for p in (gitignore_patterns or []) if p and not p.startswith("#")]

    @classmethod
    def from_root(cls, root: str) -> "IgnoreRules":
        patterns: list[str] = []
        gi = os.path.join(root, ".gitignore")
        if os.path.isfile(gi):
            try:
                with open(gi, encoding="utf-8", errors="replace") as fh:
                    patterns = [ln.strip() for ln in fh if ln.strip()]
            except OSError:
                patterns = []
        return cls(gitignore_patterns=patterns)

    def dir_ignored(self, name: str) -> bool:
        return name in self.ignore_dirs

    def _ext(self, rel: str) -> str:
        low = rel.lower()
        for ext in (".min.js",):          # two-part extensions checked first
            if low.endswith(ext):
                return ext
        return os.path.splitext(low)[1]

    def file_ignored(self, rel_path: str) -> bool:
        """``rel_path`` is POSIX-style, relative to the repository root."""
        rel = rel_path.replace(os.sep, "/")
        if self._ext(rel) in self.binary_extensions:
            return True
        parts = PurePosixPath(rel).parts
        if any(p in self.ignore_dirs for p in parts[:-1]):
            return True
        name = parts[-1] if parts else rel
        for pat in self.gitignore:
            if self._matches(pat, rel, name):
                return True
        return False

    @staticmethod
    def _matches(pattern: str, rel: str, name: str) -> bool:
        if pattern.startswith("!"):          # negation un-ignores; we only ADD ignores,
            return False                     # so a negation never causes a skip here
        pat = pattern.rstrip("/").lstrip("/")  # anchored and floating treated alike in v1
        if not pat:
            return False
        if "/" in pat:                       # path pattern, matched from the root
            return fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, pat + "/*")
        # bare name/glob: match the basename, or any path segment for a plain dir name
        if fnmatch.fnmatch(name, pat):
            return True
        return any(fnmatch.fnmatch(seg, pat) for seg in PurePosixPath(rel).parts[:-1])
