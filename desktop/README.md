# Desktop

Electron shell. It starts the Python backend on a free local port, opens the UI the backend
serves, and stops the backend when you close the window.

```bash
cd desktop
npm install
npm start          # builds the frontend, then opens the app
npm run smoke      # headless check: window loads and reaches the API
```

Needs the backend set up (see the main README) and Ollama running.

- **Data** lives in the app's user data folder (on Windows, `%APPDATA%\Local Doc Chat\data`),
  not in the repo.
- **Python** is `backend/.venv` by default. Set `LOCAL_DOC_CHAT_PYTHON` to use another one.
- `SMOKE_SCREENSHOT=out.png npm run smoke` also saves a screenshot of the window.

Not done yet: an installer. A packaged app has to bundle the backend (and the Python it needs);
until then the app runs from a checkout.
