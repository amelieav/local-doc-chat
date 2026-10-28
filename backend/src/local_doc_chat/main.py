"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="Local Doc Chat")


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the backend is running."""
    return {"status": "ok"}
