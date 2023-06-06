"""This module modifies environmental variables so that Django models can be accessed outside of Django itself.

When using this module it needs top be imported before anything Django related is imported. This should be done
automatically by isort because it is in the root directory and starts with an underscore. If issues arrise in the future
a proper fix may be found, or more underscores can be added to the name.

I hate how sketchy this is, but it is the easiest solution for consistely setting up Django without having a linter tell
me I am doing something wrong"""

# TODO: Figure out how to move this file into a better location without it breaking

from __future__ import annotations

import os

import django

os.environ["DJANGO_SETTINGS_MODULE"] = "stream_man.settings"
django.setup()


def activate_django():
    """Dummy function to make the import that acitaves Django able to bypass linters"""
