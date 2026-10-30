# Local Doc Chat

A desktop app to upload PDFs and ask questions. Answers come with citations.
Click one to open the PDF at that spot with the text highlighted. Everything
runs locally.

Work in progress.

## Layout

- `backend/` Python, FastAPI, LangGraph, Ollama, SQLite with sqlite-vec
- `frontend/` React and TypeScript
- `desktop/` Electron shell (later milestone)

## Development

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate   # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
```

Frontend:

```bash
cd frontend
npm install
npm run lint && npm run typecheck && npm run format:check
```

Copy `.env.example` to `.env` for local settings.

## License

MIT
