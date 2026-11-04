"""The file cPanel's Passenger loads; it serves the same WSGI application as gunicorn."""

import sys
from pathlib import Path

# Passenger loads this file by path rather than importing it as a module, so the
# application root is not guaranteed to be on sys.path; cPanel's own generated
# startup file inserts it for the same reason. Without it `config` is not importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.wsgi import application

__all__ = ["application"]
