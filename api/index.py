"""Vercel entrypoint for the Papla Flask app.

This file exposes the WSGI application object as ``app`` so that the
Vercel Python runtime can import and serve it.
"""

from papla_voice_web import app  # noqa: F401
