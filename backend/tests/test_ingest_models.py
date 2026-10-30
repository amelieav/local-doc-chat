import pytest
from pydantic import ValidationError

from local_doc_chat.ingest.models import Document, DocumentStatus, Page

SHA = "a" * 64


def make_document(**overrides: object) -> Document:
    fields: dict[str, object] = {
        "filename": "paper.pdf",
        "sha256": SHA,
        "size_bytes": 1234,
        "page_count": 3,
        "status": DocumentStatus.READY,
    }
    return Document.model_validate({**fields, **overrides})


def test_document_defaults_id_and_timestamp() -> None:
    document = make_document()

    assert document.id
    assert document.created_at.tzinfo is not None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("paper.pdf", "paper.pdf"),
        ("C:\\Users\\me\\paper.pdf", "paper.pdf"),
        ("../../etc/paper.pdf", "paper.pdf"),
    ],
)
def test_filename_keeps_only_final_component(raw: str, expected: str) -> None:
    assert make_document(filename=raw).filename == expected


@pytest.mark.parametrize("raw", ["", "/", "dir/.."])
def test_rejects_filenames_without_a_name(raw: str) -> None:
    with pytest.raises(ValidationError):
        make_document(filename=raw)


@pytest.mark.parametrize("sha", ["abc", "A" * 64, "g" * 64])
def test_rejects_bad_sha256(sha: str) -> None:
    with pytest.raises(ValidationError):
        make_document(sha256=sha)


@pytest.mark.parametrize("field", ["size_bytes", "page_count"])
def test_rejects_non_positive_counts(field: str) -> None:
    with pytest.raises(ValidationError):
        make_document(**{field: 0})


def test_page_numbers_start_at_one() -> None:
    document = make_document()

    with pytest.raises(ValidationError):
        Page(document_id=document.id, page_number=0, text="x")
