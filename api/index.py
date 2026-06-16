"""
Vercel serverless entrypoint — re-exports the FastAPI app from web/server.py.
Vercel's Python runtime auto-detects an ASGI app named `app` in this module.
"""
import os
import sys

_web_dir = os.path.join(os.path.dirname(__file__), "..", "web")
sys.path.insert(0, _web_dir)

from server import app  # noqa: E402
