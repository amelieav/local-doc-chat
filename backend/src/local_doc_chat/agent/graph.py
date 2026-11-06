"""Retrieve, grade, rewrite, answer: the question-answering loop as a LangGraph."""

import re
from typing import Literal, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict

from local_doc_chat.agent.model import ChatModel
from local_doc_chat.ingest.models import Word
from local_doc_chat.store.index import DocumentIndex, SearchResult

DONT_KNOW = "I don't know"

_GRADE_PROMPT = """\
Question: {question}

Passage:
{passage}

Does this passage help answer the question? Reply with only yes or no."""

_REWRITE_PROMPT = """\
The search query "{query}" found no passages that answer this question: {question}
Write one different search query that could find the answer. Reply with only the query."""

_ANSWER_PROMPT = """\
Answer the question using only the numbered passages below. After each claim, cite the passage \
it came from like [1]. If the passages do not contain the answer, reply exactly: {dont_know}

Passages:
{passages}

Question: {question}"""


_CITE_REMINDER = "\n\nYour answer must cite the passages it uses like [1]. Answer again."


class Citation(BaseModel):
    """A passage an answer relies on. `marker` is the [n] used in the answer text."""

    model_config = ConfigDict(frozen=True)

    marker: int
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int
    passage: str
    words: tuple[Word, ...]


class Answer(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    citations: tuple[Citation, ...]

    @property
    def found(self) -> bool:
        return bool(self.citations)


class _State(TypedDict):
    question: str
    query: str
    attempts: int
    results: list[SearchResult]
    relevant: list[SearchResult]
    answer: Answer | None


class DocAgent:
    """Answers questions from indexed documents, citing file, page and passage."""

    def __init__(
        self, index: DocumentIndex, model: ChatModel, *, k: int = 8, max_attempts: int = 3
    ) -> None:
        if k < 1 or max_attempts < 1:
            msg = "k and max_attempts must be at least 1"
            raise ValueError(msg)
        self._index = index
        self._model = model
        self._k = k
        self._max_attempts = max_attempts

        graph = StateGraph(_State)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("grade", self._grade)
        graph.add_node("rewrite", self._rewrite)
        graph.add_node("answer", self._answer)
        graph.add_node("give_up", self._give_up)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "grade")
        graph.add_conditional_edges("grade", self._route)
        graph.add_edge("rewrite", "retrieve")
        graph.add_edge("answer", END)
        graph.add_edge("give_up", END)
        self._graph = graph.compile()

    def ask(self, question: str) -> Answer:
        state = self._graph.invoke(
            {
                "question": question,
                "query": question,
                "attempts": 0,
                "results": [],
                "relevant": [],
                "answer": None,
            }
        )
        answer: Answer = state["answer"]
        return answer

    def _retrieve(self, state: _State) -> dict[str, object]:
        results = self._index.search(state["query"], self._k)
        return {"results": results, "attempts": state["attempts"] + 1}

    def _grade(self, state: _State) -> dict[str, object]:
        relevant = [
            r
            for r in state["results"]
            if self._model.complete(
                _GRADE_PROMPT.format(question=state["question"], passage=r.chunk.text)
            )
            .strip()
            .lower()
            .startswith("yes")
        ]
        return {"relevant": relevant}

    def _route(self, state: _State) -> Literal["answer", "rewrite", "give_up"]:
        if state["relevant"]:
            return "answer"
        return "rewrite" if state["attempts"] < self._max_attempts else "give_up"

    def _rewrite(self, state: _State) -> dict[str, object]:
        reply = self._model.complete(
            _REWRITE_PROMPT.format(query=state["query"], question=state["question"])
        )
        lines = reply.strip().splitlines()
        query = lines[0].strip().strip("\"'") if lines else ""
        return {"query": query or state["question"]}

    def _answer(self, state: _State) -> dict[str, object]:
        passages = state["relevant"]
        listing = "\n\n".join(
            f"[{n}] ({r.document.filename}, page {r.chunk.page_number})\n{r.chunk.text}"
            for n, r in enumerate(passages, start=1)
        )
        prompt = _ANSWER_PROMPT.format(
            dont_know=DONT_KNOW, passages=listing, question=state["question"]
        )

        # Only citations that point at a passage we showed the model count.
        cited: list[int] = []

        def keep_valid(match: re.Match[str]) -> str:
            number = int(match.group(1))
            if not 1 <= number <= len(passages):
                return ""
            if number not in cited:
                cited.append(number)
            return match.group(0)

        text = ""
        # Broad questions often get an answer with no [n]; ask once more before giving up.
        for suffix in ("", _CITE_REMINDER):
            cited.clear()
            reply = self._model.complete(prompt + suffix).strip()
            text = re.sub(r"\[(\d+)\]", keep_valid, reply).strip()
            if cited or text.lower().startswith(DONT_KNOW.lower()):
                break
        if not cited or text.lower().startswith(DONT_KNOW.lower()):
            return {"answer": Answer(text=DONT_KNOW, citations=())}
        citations = tuple(
            Citation(
                marker=n,
                chunk_id=passages[n - 1].chunk.id,
                document_id=passages[n - 1].document.id,
                filename=passages[n - 1].document.filename,
                page_number=passages[n - 1].chunk.page_number,
                passage=passages[n - 1].chunk.text,
                words=passages[n - 1].chunk.words,
            )
            for n in cited
        )
        return {"answer": Answer(text=text, citations=citations)}

    def _give_up(self, state: _State) -> dict[str, object]:
        return {"answer": Answer(text=DONT_KNOW, citations=())}
