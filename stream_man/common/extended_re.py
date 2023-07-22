from __future__ import annotations

# Import all of re so it can be exported, one of the few places were a wildcard import is acceptable
from re import *  # pylint: disable=W0622,W0401,W0614 # noqa: F403
from re import search
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from re import Match, Pattern


class StrictPatternFailure(Exception):
    """Raised when a strict pattern fails to match"""


def strict_search(pattern: Pattern[str] | str, string: str) -> Match[str]:
    """Scan through string looking for a match to the pattern, returning a Match object, or raise StrictPatternFailure
    if no match was found.

    Raises:
        StrictPatternFailure: If no match is found"""
    output = search(pattern, string)
    if output is None:
        raise StrictPatternFailure(f"{string} did not include {pattern}")
    return output
