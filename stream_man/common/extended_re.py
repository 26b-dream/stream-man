"""Extended regular expression module."""
from __future__ import annotations

# Import all of re so it can be exported, one of the few places were a wildcard import is acceptable
# Have to make a stupid line of code for all the linters I use that hate wildcard imports
from re import *  # type: ignore  # pylint: disable=W0622,W0401,W0614 # noqa: F403, PGH003
from re import search
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from re import Match, Pattern


class StrictPatternError(Exception):
    """Raised when a strict pattern fails to match."""


def strict_search(pattern: Pattern[str] | str, string: str) -> Match[str]:
    """Stricter version of re.search.

    If a match is found it returns the match object, otherwise it raises a StrictPatternError.

    Parameters:
    ----------
    pattern (Pattern[str] | str): The pattern to search for
    string (str): The string to search in

    Returns:
    -------
    Match[str]: The match object

    Raises:
        StrictPatternError: If no match is found
    """
    output = search(pattern, string)
    if output is None:
        error_message = f"Pattern {pattern} not found in {string}"
        raise StrictPatternError(error_message)
    return output
