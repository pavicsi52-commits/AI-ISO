"""Notification center service entrypoint.

Run with:

    uv run uvicorn main:app --host 0.0.0.0 --port 8026 --reload
"""

from __future__ import annotations

from app.core.factory import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    from app.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.service.host,
        port=settings.service.port,
        reload=settings.application.debug,
    )
