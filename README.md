# Local Doc Chat
<img width="1545" height="706" alt="image" src="https://github.com/user-attachments/assets/cbc1b583-26b8-44b6-b8c4-9d8ffc269060" />

A locally hosted webapp to upload PDFs and ask questions. Answers come with citations.
Click one to open the PDF at that spot with the text highlighted.

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

## Retrieval eval

`backend/eval/dataset.json` holds generated documents plus questions about a real report. Score
retrieval (needs Ollama with the embedding model), or add `--answers` to also check the chat
model's answers:

```bash
cd backend
python -m local_doc_chat.evaluation [--answers]
```

`backend/eval/pdfs/GlobalEnergyReview2025.pdf` is the IEA's Global Energy Review 2025, used under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## License

MIT
