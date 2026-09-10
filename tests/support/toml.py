"""Small TOML compatibility adapter for the Python 3.10 test floor."""

import importlib

try:
    load = importlib.import_module("tomllib").load
except ModuleNotFoundError:
    load = importlib.import_module("tomli").load
