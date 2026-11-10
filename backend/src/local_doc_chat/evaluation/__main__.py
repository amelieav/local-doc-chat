"""Run the retrieval eval: `python -m local_doc_chat.evaluation`."""

import argparse
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from local_doc_chat.evaluation.runner import build_index, evaluate, load_dataset
from local_doc_chat.store.embeddings import EmbeddingError, OllamaEmbedder


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score retrieval against a question set.")
    parser.add_argument("--dataset", type=Path, default=Path("eval/dataset.json"))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument(
        "--min-hit-rate", type=float, default=0.0, help="exit 1 if hit rate is below this"
    )
    parser.add_argument("--min-mrr", type=float, default=0.0, help="exit 1 if MRR is below this")
    args = parser.parse_args(argv)

    dataset = load_dataset(args.dataset)
    embedder = OllamaEmbedder(
        os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            report = evaluate(dataset, build_index(dataset, embedder, Path(tmp)), args.k)
    except EmbeddingError as exc:
        print(f"Embedding failed: {exc}")
        return 2

    for miss in report.misses:
        print(
            f"MISS: {miss.question.question} (want {miss.question.document} p{miss.question.page})"
        )
    print(
        f"questions={len(report.results)} hit@{report.k}={report.hit_rate:.2f} "
        f"top1={report.top1:.2f} mrr={report.mrr:.2f}"
    )
    return 0 if report.hit_rate >= args.min_hit_rate and report.mrr >= args.min_mrr else 1


if __name__ == "__main__":
    raise SystemExit(main())
