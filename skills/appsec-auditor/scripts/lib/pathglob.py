"""Minimal glob matching for repo-relative paths with forward slashes.

Supports **, *, ?, {a,b}, and character classes [...]. A glob without "/" matches the base name.
The module is named pathglob so it never shadows the standard library glob.

Public API:
    glob_to_regexp(glob) -> re.Pattern[str]
    matches(rel_path, glob) -> bool
    matches_any(rel_path, globs) -> bool
"""

from __future__ import annotations

import functools
import re
import warnings
from collections.abc import Iterable

__all__ = ['glob_to_regexp', 'matches', 'matches_any']

# Characters that must be escaped to match literally in a regular expression.
RE_SPECIAL: re.Pattern[str] = re.compile(r'[.+^$()|\\]')


def class_regex(inner: str) -> str:
    """Regex for the inside of a glob [...] class; '[]' matches nothing and '[^]' anything."""
    if inner == '':
        return '(?!)'
    if inner == '^':
        return '.'
    return '[' + inner.replace('\\', '\\\\') + ']'


def glob_body(glob: str) -> str:
    """Regular-expression source (without anchors) for a glob."""
    out: list[str] = []
    i = 0
    while i < len(glob):
        c = glob[i]
        if c == '*':
            if glob[i + 1:i + 2] == '*':
                # "**/" matches zero or more directories; a trailing "**" matches everything below.
                if glob[i + 2:i + 3] == '/':
                    out.append('(?:.*/)?')
                    i += 2
                else:
                    out.append('.*')
                    i += 1
            else:
                out.append('[^/]*')
        elif c == '?':
            out.append('[^/]')
        elif c in '{[':
            close = '}' if c == '{' else ']'
            end = glob.find(close, i)
            if end < 0:
                out.append('\\' + c)
            else:
                inner = glob[i + 1:end]
                if c == '{':
                    out.append('(?:' + '|'.join(glob_body(alt) for alt in inner.split(',')) + ')')
                else:
                    out.append(class_regex(inner))
                i = end
        else:
            out.append(RE_SPECIAL.sub(lambda m: '\\' + m[0], c))
        i += 1
    return ''.join(out)


@functools.lru_cache(maxsize=None)
def glob_to_regexp(glob: str) -> re.Pattern[str]:
    """Compile a glob into an anchored regular expression (raises re.error for a bad class)."""
    with warnings.catch_warnings():
        # Classes such as "[a--b]" or "[[]" are literal here; Python only warns about them.
        warnings.simplefilter('ignore', FutureWarning)
        return re.compile(rf'^{glob_body(glob)}\Z')


def matches(rel_path: str, glob: str) -> bool:
    """True when the glob matches the path (or its base name when the glob has no slash)."""
    target = rel_path if '/' in glob else rel_path.rpartition('/')[2]
    return glob_to_regexp(glob).search(target) is not None


def matches_any(rel_path: str, globs: Iterable[str] | None) -> bool:
    """True when any glob matches the path."""
    return any(matches(rel_path, g) for g in globs or [])
