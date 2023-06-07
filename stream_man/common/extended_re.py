"""This module is a wrapper around the re module that adds some extra functionality."""

from __future__ import annotations

# Import all of re so it can be exported
# This will cause a lot of pylint errors
from re import compile  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611, W0622
from re import escape  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611
from re import findall  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611
from re import finditer  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611
from re import fullmatch  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611
from re import match  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611
from re import purge  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611
from re import search  # pylint: disable=C0414, W0611
from re import split  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611
from re import sub  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611
from re import subn  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611
from re import template  # pyright: ignore[reportUnusedImport] # pylint: disable=C0414, W0611
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from re import Match, Pattern


class StrictPatternFailure(Exception):
    """Raised when a strict pattern fails to match""" ""


def strict_search(pattern: Pattern[str] | str, string: str) -> Match[str]:
    """Scan through string looking for a match to the pattern, returning a Match object, or raise StrictPatternFailure
    if no match was found.

    Args:
        pattern (Pattern[str] | str): The pattern to search for
        string (str): The string to search in

    Raises:
        StrictPatternFailure: If no match is found

    Returns:
        Match[str]: The match object
    """
    output = search(pattern, string)
    if output is None:
        raise StrictPatternFailure(f"{string} did not include {pattern}")
    return output
