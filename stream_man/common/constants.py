"""Contains useful constants."""

from __future__ import annotations

from paved_path import PavedPath

from stream_man.settings import BASE_DIR as _BASE_DIR

BASE_DIR = PavedPath(_BASE_DIR)
DOWNLOADED_FILES_DIR = BASE_DIR / "downloaded_files"
