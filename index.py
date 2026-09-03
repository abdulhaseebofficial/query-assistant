"""Vercel Flask framework entry point.

Modern Vercel Flask deployments discover a root ``index.py`` and preserve the
original request path for Flask routing. ``api.index`` remains the explicit WSGI
entry point used by local deployment checks and compatible integrations.
"""

from api.index import app

__all__ = ["app"]
