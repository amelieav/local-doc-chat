from pathlib import Path

import pytest

from fakes import HashingEmbedder, ScriptedModel
from local_doc_chat.agent.graph import DONT_KNOW, DocAgent
from local_doc_chat.evaluation.runner import EvalDataset, build_index
from local_doc_chat.store.index import DocumentIndex

GRADE = "Does this passage help"
REWRITE = "Write one different search query"
ANSWER = "Answer the question using only"


@pytest.fixture
def index(tmp_path: Path) -> DocumentIndex:
    dataset = EvalDataset.model_validate(
        {
            "documents": [
                {
                    "name": "pets.pdf",
                    "pages": ["cats purr and sleep all day", "dogs bark and chase balls"],
                }
            ],
            "questions": [{"question": "q", "document": "pets.pdf", "page": 1}],
        }
    )
    return build_index(dataset, HashingEmbedder(), tmp_path)


def dog_judge(prompt: str) -> str:
    """Says yes to the dog passage only."""
    return "Yes." if "dogs bark" in prompt else "No."


def test_answers_with_citation(index: DocumentIndex) -> None:
    def reply(prompt: str) -> str:
        if GRADE in prompt:
            return dog_judge(prompt)
        assert ANSWER in prompt
        assert "cats purr" not in prompt  # only graded-relevant passages reach the answer step
        return "Dogs bark and chase balls [1]."

    model = ScriptedModel(reply)

    answer = DocAgent(index, model, k=2).ask("what do dogs do")

    assert answer.found
    assert answer.text == "Dogs bark and chase balls [1]."
    (citation,) = answer.citations
    assert (citation.marker, citation.filename, citation.page_number) == (1, "pets.pdf", 2)
    assert citation.passage == "dogs bark and chase balls"
    assert [w.text for w in citation.words] == ["dogs", "bark", "and", "chase", "balls"]
    assert (model.count(GRADE), model.count(REWRITE), model.count(ANSWER)) == (2, 0, 1)


def test_rewrites_the_question_when_nothing_is_relevant(index: DocumentIndex) -> None:
    rewritten = False

    def reply(prompt: str) -> str:
        nonlocal rewritten
        if REWRITE in prompt:
            rewritten = True
            return '"dogs bark"\nsome extra line'
        if GRADE in prompt:
            return dog_judge(prompt) if rewritten else "No"
        return "Dogs bark [1]."

    model = ScriptedModel(reply)

    answer = DocAgent(index, model, k=2).ask("tell me about the canine")

    assert answer.found
    assert (model.count(GRADE), model.count(REWRITE), model.count(ANSWER)) == (4, 1, 1)


def test_gives_up_after_max_attempts(index: DocumentIndex) -> None:
    model = ScriptedModel(lambda p: "No" if GRADE in p else "some other query")

    answer = DocAgent(index, model, k=2, max_attempts=2).ask("anything")

    assert answer.text == DONT_KNOW
    assert not answer.found
    # two searches of two passages each, one rewrite between them, and no answer attempt
    assert (model.count(GRADE), model.count(REWRITE), model.count(ANSWER)) == (4, 1, 0)


def test_answer_without_a_citation_is_rejected(index: DocumentIndex) -> None:
    model = ScriptedModel(lambda p: dog_judge(p) if GRADE in p else "Dogs bark.")

    answer = DocAgent(index, model, k=2).ask("what do dogs do")

    assert answer.text == DONT_KNOW
    assert not answer.found


def test_uncited_answer_is_retried_once_with_a_reminder(index: DocumentIndex) -> None:
    def reply(prompt: str) -> str:
        if GRADE in prompt:
            return dog_judge(prompt)
        return "Dogs bark [1]." if "must cite" in prompt else "Dogs bark."

    model = ScriptedModel(reply)

    answer = DocAgent(index, model, k=2).ask("what do dogs do")

    assert answer.text == "Dogs bark [1]."
    assert model.count(ANSWER) == 2


def test_citation_to_an_unseen_passage_is_dropped(index: DocumentIndex) -> None:
    model = ScriptedModel(
        lambda p: dog_judge(p) if GRADE in p else "Dogs bark [1] and cats purr [7]."
    )

    answer = DocAgent(index, model, k=2).ask("what do dogs do")

    assert "[7]" not in answer.text
    assert [c.marker for c in answer.citations] == [1]


def test_model_saying_it_does_not_know(index: DocumentIndex) -> None:
    model = ScriptedModel(lambda p: dog_judge(p) if GRADE in p else "I don't know")

    answer = DocAgent(index, model, k=2).ask("what is the capital of France")

    assert answer.text == DONT_KNOW
    assert not answer.found


@pytest.mark.parametrize("kwargs", [{"k": 0}, {"max_attempts": 0}])
def test_rejects_bad_settings(index: DocumentIndex, kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        DocAgent(index, ScriptedModel(lambda _: ""), **kwargs)
