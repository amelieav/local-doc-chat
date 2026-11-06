"""Load an eval dataset, index it, and score retrieval against it."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from local_doc_chat.evaluation.pdfgen import make_pdf
from local_doc_chat.ingest.extraction import PdfplumberExtractor
from local_doc_chat.ingest.service import IngestService
from local_doc_chat.ingest.validation import PdfLimits
from local_doc_chat.store.documents import SqliteDocumentStore
from local_doc_chat.store.embeddings import Embedder
from local_doc_chat.store.index import DocumentIndex
from local_doc_chat.store.vectors import SqliteVecStore


class EvalDocument(BaseModel):
    name: str
    pages: list[str] = Field(min_length=1)


class EvalQuestion(BaseModel):
    """A question and the page that answers it. Pages start at 1."""

    question: str
    document: str
    page: int = Field(ge=1)


class EvalDataset(BaseModel):
    documents: list[EvalDocument] = Field(min_length=1)
    questions: list[EvalQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def questions_point_at_real_pages(self) -> Self:
        pages = {d.name: len(d.pages) for d in self.documents}
        for q in self.questions:
            if q.page > pages.get(q.document, 0):
                msg = f"Question {q.question!r} points at missing {q.document} page {q.page}"
                raise ValueError(msg)
        return self


class QuestionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: EvalQuestion
    rank: int | None  # 1-based position of the right page in the top k, else None


class EvalReport(BaseModel):
    k: int
    results: list[QuestionResult]

    @property
    def hit_rate(self) -> float:
        """Share of questions whose right page is in the top k."""
        return sum(r.rank is not None for r in self.results) / len(self.results)

    @property
    def top1(self) -> float:
        return sum(r.rank == 1 for r in self.results) / len(self.results)

    @property
    def mrr(self) -> float:
        """Mean reciprocal rank: 1 for first place, 0.5 for second, 0 for a miss."""
        return sum(1 / r.rank if r.rank else 0 for r in self.results) / len(self.results)

    @property
    def misses(self) -> list[QuestionResult]:
        return [r for r in self.results if r.rank is None]


def load_dataset(path: Path) -> EvalDataset:
    return EvalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def build_index(dataset: EvalDataset, embedder: Embedder, root: Path) -> DocumentIndex:
    """Ingest and index every dataset document into fresh stores under root."""
    documents = SqliteDocumentStore(root / "db.sqlite", root / "pdfs")
    dimensions = len(embedder.embed_query("dimension probe"))
    index = DocumentIndex(documents, SqliteVecStore(root / "vectors.sqlite", dimensions), embedder)
    service = IngestService(PdfplumberExtractor(), documents, PdfLimits())
    for doc in dataset.documents:
        index.index_document(service.ingest(make_pdf(doc.pages), doc.name).document.id)
    return index


def evaluate(dataset: EvalDataset, index: DocumentIndex, k: int = 5) -> EvalReport:
    results = []
    for q in dataset.questions:
        hits = index.search(q.question, k)
        rank = next(
            (
                position
                for position, hit in enumerate(hits, start=1)
                if hit.document.filename == q.document and hit.chunk.page_number == q.page
            ),
            None,
        )
        results.append(QuestionResult(question=q, rank=rank))
    return EvalReport(k=k, results=results)
