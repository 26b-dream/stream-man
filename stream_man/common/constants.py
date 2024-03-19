"""Constants used throughout the project."""

from __future__ import annotations

from paved_path import PavedPath

from stream_man.settings import BASE_DIR as _BASE_DIR

# Update the value to use PavedPath instead of a regular path
BASE_DIR = PavedPath(_BASE_DIR)

DOWNLOADED_FILES_DIR = BASE_DIR / "downloaded_files"
