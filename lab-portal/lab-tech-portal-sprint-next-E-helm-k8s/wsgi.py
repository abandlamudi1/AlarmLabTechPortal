# wsgi.py — WSGI entrypoint for Gunicorn (Slice G-part1, issue #5)
# Pattern: standard Flask WSGI entrypoint; no guide pattern citation needed.
from app import app  # noqa: F401  (re-exported as the WSGI callable)
