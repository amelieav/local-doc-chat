from pathlib import Path

import pytest
from pydantic import ValidationError

from fakes import HashingEmbedder, ScriptedModel
from local_doc_chat.agent.graph import DocAgent
from local_doc_chat.evaluation.pdfgen import make_pdf
from local_doc_chat.evaluation.runner import (
    EvalDataset,
    EvalQuestion,
    EvalReport,
    QuestionResult,
    build_index,
    evaluate,
    evaluate_answers,
    load_dataset,
)
from local_doc_chat.ingest.extraction import PdfplumberExtractor
from local_doc_chat.ingest.validation import PdfLimits

DATASET_PATH = Path(__file__).parents[1] / "eval" / "dataset.json"


def question(page: int = 1) -> EvalQuestion:
    return EvalQuestion(question="q", document="a.pdf", page=page)


def test_pdfgen_wraps_long_text_and_escapes_parentheses() -> None:
    text = "start (inside) back\\slash " + "word " * 80 + "end"

    (page,) = PdfplumberExtractor().extract(make_pdf([text]), PdfLimits())

    assert page.text.split() == text.split()
    assert all(w.x0 >= 0 and w.x1 <= page.width for w in page.words)


def test_report_metrics() -> None:
    report = EvalReport(
        k=5,
        results=[
            QuestionResult(question=question(), rank=1),
            QuestionResult(question=question(), rank=2),
            QuestionResult(question=question(), rank=None),
        ],
    )

    assert report.hit_rate == pytest.approx(2 / 3)
    assert report.top1 == pytest.approx(1 / 3)
    assert report.mrr == pytest.approx(0.5)
    assert len(report.misses) == 1


def test_dataset_rejects_question_about_missing_page() -> None:
    with pytest.raises(ValidationError, match="missing"):
        EvalDataset.model_validate(
            {
                "documents": [{"name": "a.pdf", "pages": ["one"]}],
                "questions": [{"question": "q", "document": "a.pdf", "page": 2}],
            }
        )


def test_bundled_dataset_is_valid() -> None:
    dataset = load_dataset(DATASET_PATH)

    assert len(dataset.documents) >= 3
    assert len(dataset.questions) >= 15


def test_evaluate_scores_a_tiny_dataset(tmp_path: Path) -> None:
    dataset = EvalDataset.model_validate(
        {
            "documents": [{"name": "a.pdf", "pages": ["apples oranges bananas", "trains boats"]}],
            "questions": [
                {"question": "bananas and apples", "document": "a.pdf", "page": 1},
                {"question": "boats", "document": "a.pdf", "page": 2},
                {"question": "boats", "document": "a.pdf", "page": 1},
            ],
        }
    )
    index = build_index(dataset, HashingEmbedder(), tmp_path)

    report = evaluate(dataset, index, k=1)

    assert [r.rank for r in report.results] == [1, 1, None]
    assert report.hit_rate == pytest.approx(2 / 3)


def test_document_needs_exactly_one_of_pages_or_path() -> None:
    with pytest.raises(ValidationError, match="either pages or path"):
        EvalDataset.model_validate(
            {
                "documents": [{"name": "a.pdf"}],
                "questions": [{"question": "q", "document": "a.pdf", "page": 1}],
            }
        )


def test_real_pdf_documents_load_relative_to_the_dataset(tmp_path: Path) -> None:
    (tmp_path / "real.pdf").write_bytes(make_pdf(["apples oranges bananas"]))
    (tmp_path / "set.json").write_text(
        '{"documents": [{"name": "real.pdf", "path": "real.pdf"}],'
        ' "questions": [{"question": "apples", "document": "real.pdf", "page": 1}]}',
        encoding="utf-8",
    )

    dataset = load_dataset(tmp_path / "set.json")
    index = build_index(dataset, HashingEmbedder(), tmp_path / "work")

    assert evaluate(dataset, index, k=1).hit_rate == 1


def test_evaluate_answers_checks_text_and_citation(tmp_path: Path) -> None:
    dataset = EvalDataset.model_validate(
        {
            "documents": [{"name": "a.pdf", "pages": ["apples are red", "boats float"]}],
            "questions": [
                {"question": "apples", "document": "a.pdf", "page": 1, "expect": ["RED"]},
                {"question": "boats", "document": "a.pdf", "page": 2, "expect": ["sink"]},
                {"question": "no expectation", "document": "a.pdf", "page": 1},
            ],
        }
    )
    index = build_index(dataset, HashingEmbedder(), tmp_path)
    model = ScriptedModel(lambda p: "Yes" if "Does this passage help" in p else "It is red [1].")

    report = evaluate_answers(dataset, DocAgent(index, model, k=2))

    assert [(r.correct, r.cited) for r in report.results] == [(True, True), (False, True)]
    assert report.correct_rate == pytest.approx(0.5)
