"""Error pattern matching — auto-surfaces known workarounds.

Patterns are stored as working memory entries with a prefix:
  ``error-pattern: <regex> → <fix description>``
"""

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_PATTERN_PREFIX = "error-pattern: "
_PATTERN_ARROW = " → "


def extract_patterns(working_entries: List[str]) -> List[Tuple[re.Pattern, str]]:
    """Parse error-pattern entries from working memory.

    Returns a list of (compiled_regex, fix_description) tuples.
    """
    patterns = []
    for entry in working_entries:
        if not entry.startswith(_PATTERN_PREFIX):
            continue
        body = entry[len(_PATTERN_PREFIX):]
        if _PATTERN_ARROW not in body:
            continue
        regex_str, fix = body.split(_PATTERN_ARROW, 1)
        try:
            patterns.append((re.compile(regex_str.strip(), re.IGNORECASE), fix.strip()))
        except re.error:
            logger.debug("error-pattern: invalid regex '%s'", regex_str.strip())
            continue
    return patterns


def check_error(stderr: str, working_entries: List[str]) -> Optional[str]:
    """Scan *stderr* against known error patterns.

    Returns a hint string if a pattern matches, or None.
    """
    patterns = extract_patterns(working_entries)
    if not patterns:
        return None

    tail = stderr[-2000:] if len(stderr) > 2000 else stderr

    matches = []
    for regex, fix in patterns:
        if regex.search(tail):
            matches.append(fix)

    if not matches:
        return None

    return "\n💡 Known workaround(s):\n" + "\n".join(
        f"  • {m}" for m in matches
    )
