#!/usr/bin/env python3
"""android-walkthrough entry point: python aw.py <command> ...  (see SKILL.md)."""

import os
import sys

# Works even under `python -I` / `-P`, where the script directory is not on sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aw.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
