import mimetypes
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fakes import HashingEmbedder, ScriptedModel
from local_doc_chat.desktop import create_desktop_app
from local_doc_chat.main import Settings


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<h1>Local Doc Chat</h1>", encoding="utf-8")
    (dist / "assets" / "worker.mjs").write_text("export {};", encoding="utf-8")
    app = create_desktop_app(
        dist,
        settings=Settings(data_dir=tmp_path / "data", embed_dimensions=64),
        embedder=HashingEmbedder(),
        model=ScriptedModel(lambda _prompt: "No"),
    )
    return TestClient(app)


def test_serves_frontend_and_api_on_one_origin(client: TestClient) -> None:
    assert "Local Doc Chat" in client.get("/").text
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/documents").json() == []


def test_module_workers_get_a_javascript_mime_type(client: TestClient) -> None:
    response = client.get("/assets/worker.mjs")

    assert response.headers["content-type"].startswith("text/javascript")
    assert mimetypes.guess_type("x.mjs")[0] == "text/javascript"


def test_missing_frontend_build_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="npm run build"):
        create_desktop_app(tmp_path / "nope")
