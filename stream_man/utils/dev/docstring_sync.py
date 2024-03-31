"""Finds docstrings that differ between the scrapers."""
from __future__ import annotations

import inspect

import _activate_django  # pyright: ignore[reportUnusedImport]  # noqa: F401
from common.abstract_scraper import AbstractScraperClass
from common.get_scraper import import_scrapers

# This is something I debated about a long time. I want all of the scrapers to have the same docstring, but could not
# decided on the best way to achieve this goal. I thought about having docstrings in the base class, but that doesn't
# work because different scrapers may have different parameters which would require a different docstring. I also
# considered making a multitude of classes that each contain an abstract function that contains just a docstring that
# can be imported, but that makes initilizing the class really ugly and it can be hard to remember to import all of the
# docstrings. In the end I decided to keep the docstrings in sync manually, this is just a quick little script that will
# take all of the docstrings for each function and compare them. If a docstring does not match it will be listed.
if __name__ == "__main__":
    import_scrapers()
    functions: dict[str, str | None] = {}
    for subclass in AbstractScraperClass.__subclasses__():
        for _scraper_name, function in vars(subclass).items():
            if inspect.isfunction(function):
                key = function.__name__ + str(function.__annotations__)
                docstring = inspect.getdoc(function)
                if functions.get(key) and functions.get(key) != docstring:
                    print(function)  # noqa: T201 - The purpose of this script is to print
                else:
                    functions[key] = docstring
