#!/usr/bin/env python3
"""Abraham watcher. Input design: docs/r13-inputs/watchers/watch-live.py at 5bf44ec."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live_watch import ABRAHAM, main

if __name__ == "__main__":
    raise SystemExit(main(ABRAHAM))
