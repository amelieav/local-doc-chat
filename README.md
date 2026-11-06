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
python -m venv .venv     # Windows: py -3.12 -m venv .venv (MSYS2 Python has no sqlite-vec wheel)
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

Settings are read from environment variables; see `.env.example` for the names and defaults.

Run the app (needs Ollama running with `nomic-embed-text` and a chat model pulled):

```bash
# terminal 1, from backend/
.venv/Scripts/python -m uvicorn local_doc_chat.main:create_app --factory --port 8000
# terminal 2, from frontend/
npm run dev
```

Then open http://localhost:5173.

## License

MIT
