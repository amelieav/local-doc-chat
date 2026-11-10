"""Entry point for the desktop app: the API under /api and the built frontend at /, one origin.

Run with `uvicorn local_doc_chat.desktop:create_desktop_app --factory`; set FRONTEND_DIR to the
frontend's `dist` folder.
"""

import mimetypes
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from local_doc_chat.main import create_app

# Windows can map .mjs to text/plain, which browsers refuse for module scripts (the PDF worker).
mimetypes.add_type("text/javascript", ".mjs")


def create_desktop_app(frontend_dir: Path | None = None, **kwargs: Any) -> FastAPI:  # noqa: ANN401
    """`kwargs` go to `create_app` (settings, embedder, model)."""
    directory = frontend_dir or Path(os.environ.get("FRONTEND_DIR", "frontend/dist"))
    if not (directory / "index.html").is_file():
        msg = f"No built frontend at {directory}; run `npm run build` in frontend/"
        raise FileNotFoundError(msg)
    app = FastAPI(title="Local Doc Chat desktop")
    # The frontend calls /api/...; the API app itself serves the same routes without the prefix.
    app.mount("/api", create_app(**kwargs))
    app.mount("/", StaticFiles(directory=directory, html=True))
    return app
