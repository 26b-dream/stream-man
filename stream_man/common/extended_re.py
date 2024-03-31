"""Contains an extended version of re."""
from __future__ import annotations

# Import all of re so it can be exported, one of the few places were a wildcard import is acceptable
# Have to make a stupid line of code for all the linters I use that hate wildcard imports
from re import *  # type: ignore # noqa: F403, PGH003
from re import search
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Private value is imported just to be used as a type hint. This should be safe even if the original package removed
    # the private value.
    from re import Match, Pattern, _FlagsType  # type: ignore[reportPrivateUsage]


class StrictPatternError(Exception):
    """Raised when a strict pattern fails to match."""


def strict_search(pattern: Pattern[str] | str, string: str, flags: _FlagsType | None = None) -> Match[str]:
    """Stricter version of re.search that raises a StrictPatternError if no match is found.

    Raises:
        StrictPatternError: If no match is found
    """
    # Only pass flags if is set
    output = search(pattern, string, flags) if flags else search(pattern, string)

    if output is None:
        error_message = f"Pattern {pattern} not found in {string}"
        raise StrictPatternError(error_message)
    return output
