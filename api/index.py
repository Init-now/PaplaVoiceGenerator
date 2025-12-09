"""Vercel entrypoint for the Papla Flask app.

This file exposes the WSGI application object as ``app`` so that the
Vercel Python runtime can import and serve it.
"""

from web_app import app  # noqa: F401
