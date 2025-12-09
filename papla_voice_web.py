"""Compatibility shim for legacy entrypoints.

Vercel and the local run script historically imported ``app`` from this file.
The actual Flask application now lives in ``web_app.py``. This module simply
re-exports the app (and keeps the __main__ launcher) so imports don't fail.
"""

from web_app import app, make_app  # re-export for legacy imports


if __name__ == "__main__":
    # Mirror the behavior in web_app.py for local runs
    import os

    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=5003, debug=debug)
