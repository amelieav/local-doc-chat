// Electron shell: starts the Python backend on a free local port, shows the UI it serves,
// and stops the backend when the app quits.
const { app, BrowserWindow, dialog, shell } = require("electron");
const { spawn } = require("node:child_process");
const net = require("node:net");
const path = require("node:path");

const root = path.join(__dirname, "..");
const smoke = process.argv.includes("--smoke");
const STARTUP_TIMEOUT_MS = 60_000;

/** @type {import("node:child_process").ChildProcess | null} */
let backend = null;
let backendLog = "";

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => {
        resolve(port);
      });
    });
  });
}

// shortcut: runs the dev virtualenv; a packaged app needs the backend bundled, see milestone 9.
function pythonPath() {
  if (process.env.LOCAL_DOC_CHAT_PYTHON) {
    return process.env.LOCAL_DOC_CHAT_PYTHON;
  }
  const venv = path.join(root, "backend", ".venv");
  return process.platform === "win32"
    ? path.join(venv, "Scripts", "python.exe")
    : path.join(venv, "bin", "python");
}

function startBackend(port) {
  const child = spawn(
    pythonPath(),
    [
      "-m",
      "uvicorn",
      "local_doc_chat.desktop:create_desktop_app",
      "--factory",
      "--host",
      "127.0.0.1",
      "--port",
      String(port),
    ],
    {
      cwd: path.join(root, "backend"),
      env: {
        ...process.env,
        DATA_DIR: path.join(app.getPath("userData"), "data"),
        FRONTEND_DIR: path.join(root, "frontend", "dist"),
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  const keep = (chunk) => {
    backendLog = (backendLog + String(chunk)).slice(-4000);
  };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);
  return child;
}

async function waitForBackend(port, child) {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`The backend stopped while starting.\n\n${backendLog}`);
    }
    try {
      const response = await fetch(`http://127.0.0.1:${String(port)}/api/health`);
      if (response.ok) {
        return;
      }
    } catch {
      // Not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`The backend did not start within a minute.\n\n${backendLog}`);
}

function openWindow(origin) {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: "#f3e6ef",
    show: !smoke,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  // Keep the window on our own origin; send real web links to the user's browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(origin)) {
      event.preventDefault();
    }
  });
  void win.loadURL(origin);
  return win;
}

/** Stop the backend, then exit at once without waiting for windows. */
function shutdown(code) {
  backend?.kill();
  app.exit(code);
}

/** `--smoke`: load the page, check it rendered and can reach the API, print the result, exit. */
async function runSmokeTest(win) {
  if (win.webContents.isLoading()) {
    await new Promise((resolve) => win.webContents.once("did-finish-load", resolve));
  }
  const result = await win.webContents.executeJavaScript(`(async () => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    const response = await fetch("/api/documents");
    return {
      title: document.title,
      heading: document.querySelector("h1")?.textContent,
      apiStatus: response.status,
    };
  })()`);
  if (process.env.SMOKE_SCREENSHOT) {
    const image = await win.webContents.capturePage();
    require("node:fs").writeFileSync(process.env.SMOKE_SCREENSHOT, image.toPNG());
  }
  const ok = Boolean(result.heading) && result.apiStatus === 200;
  console.log(`SMOKE ${ok ? "ok" : "FAILED"} ${JSON.stringify(result)}`);
  shutdown(ok ? 0 : 1);
}

async function main() {
  if (!app.requestSingleInstanceLock()) {
    app.quit();
    return;
  }
  await app.whenReady();
  try {
    const port = await freePort();
    backend = startBackend(port);
    await waitForBackend(port, backend);
    const win = openWindow(`http://127.0.0.1:${String(port)}`);
    if (smoke) {
      await runSmokeTest(win);
    }
  } catch (error) {
    if (smoke) {
      console.error(`SMOKE FAILED ${error.message}`);
      shutdown(1);
      return;
    }
    dialog.showErrorBox("Local Doc Chat could not start", error.message);
    app.quit();
  }
}

app.on("window-all-closed", () => {
  app.quit();
});
app.on("before-quit", () => {
  backend?.kill();
});

void main();
