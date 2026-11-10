"""Load an eval dataset, index it, and score retrieval against it."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from local_doc_chat.agent.graph import DocAgent
from local_doc_chat.evaluation.pdfgen import make_pdf
from local_doc_chat.ingest.extraction import PdfplumberExtractor
from local_doc_chat.ingest.service import IngestService
from local_doc_chat.ingest.validation import PdfLimits
from local_doc_chat.store.documents import SqliteDocumentStore
from local_doc_chat.store.embeddings import Embedder
from local_doc_chat.store.index import DocumentIndex
from local_doc_chat.store.vectors import SqliteVecStore


class EvalDocument(BaseModel):
    """Either `pages` (text we turn into a PDF) or `path` (a real PDF, relative to the dataset)."""

    name: str
    pages: list[str] = []
    path: Path | None = None

    @model_validator(mode="after")
    def has_pages_or_path(self) -> Self:
        if bool(self.pages) == (self.path is not None):
            msg = f"{self.name}: give either pages or path"
            raise ValueError(msg)
        return self

    def pdf_bytes(self) -> bytes:
        return self.path.read_bytes() if self.path else make_pdf(self.pages)


class EvalQuestion(BaseModel):
    """A question and the page that answers it. Pages start at 1.

    `expect` are strings a correct answer must contain (any case); only used by `--answers`.
    """

    question: str
    document: str
    page: int = Field(ge=1)
    expect: list[str] = []


class EvalDataset(BaseModel):
    documents: list[EvalDocument] = Field(min_length=1)
    questions: list[EvalQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def questions_point_at_real_pages(self) -> Self:
        # shortcut: page numbers of real PDFs are not checked here, a bad one just scores a miss.
        pages = {d.name: len(d.pages) or None for d in self.documents}
        for q in self.questions:
            if q.document not in pages or (pages[q.document] or q.page) < q.page:
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
    dataset = EvalDataset.model_validate_json(path.read_text(encoding="utf-8"))
    for doc in dataset.documents:
        if doc.path:
            doc.path = path.parent / doc.path
    return dataset


def build_index(dataset: EvalDataset, embedder: Embedder, root: Path) -> DocumentIndex:
    """Ingest and index every dataset document into fresh stores under root."""
    documents = SqliteDocumentStore(root / "db.sqlite", root / "pdfs")
    dimensions = len(embedder.embed_query("dimension probe"))
    index = DocumentIndex(documents, SqliteVecStore(root / "vectors.sqlite", dimensions), embedder)
    service = IngestService(PdfplumberExtractor(), documents, PdfLimits())
    for doc in dataset.documents:
        index.index_document(service.ingest(doc.pdf_bytes(), doc.name).document.id)
    return index


class AnswerResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: EvalQuestion
    answer: str
    correct: bool  # the answer contains every expected string
    cited: bool  # a citation points at the right document and page


class AnswerReport(BaseModel):
    results: list[AnswerResult]

    @property
    def correct_rate(self) -> float:
        return sum(r.correct for r in self.results) / len(self.results)

    @property
    def cited_rate(self) -> float:
        return sum(r.cited for r in self.results) / len(self.results)


def evaluate_answers(dataset: EvalDataset, agent: DocAgent) -> AnswerReport:
    """Ask the agent every question that has `expect` strings and check its answer."""
    results = []
    for q in (q for q in dataset.questions if q.expect):
        answer = agent.ask(q.question)
        results.append(
            AnswerResult(
                question=q,
                answer=answer.text,
                correct=all(e.lower() in answer.text.lower() for e in q.expect),
                cited=any(
                    c.filename == q.document and c.page_number == q.page for c in answer.citations
                ),
            )
        )
    return AnswerReport(results=results)


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
