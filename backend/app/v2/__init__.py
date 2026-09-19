"""Carbon Lens /api/v2.

This package is additive: it never imports from, mutates or re-registers anything
in the frozen /api/v1 application. `backend.app.main.create_app` keeps returning
exactly the v1 routes; the Lens application is built separately and composed at
the process entry point (`backend/serve.py`).
"""
