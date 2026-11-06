"""Split extracted pages into overlapping word windows."""

from collections.abc import Sequence
from uuid import UUID

from local_doc_chat.ingest.models import Chunk, ExtractedPage


def chunk_pages(
    document_id: UUID,
    pages: Sequence[ExtractedPage],
    *,
    max_words: int = 100,
    overlap: int = 20,
) -> list[Chunk]:
    """Chunks never cross a page, so every chunk cites one page.

    shortcut: windows ignore sentence boundaries, upgrade if retrieval quality needs it.
    """
    if not 0 <= overlap < max_words:
        msg = "overlap must be at least 0 and less than max_words"
        raise ValueError(msg)
    step = max_words - overlap
    chunks: list[Chunk] = []
    for page in pages:
        for start in range(0, len(page.words), step):
            window = page.words[start : start + max_words]
            chunks.append(
                Chunk(
                    document_id=document_id,
                    chunk_index=len(chunks),
                    page_number=page.page_number,
                    text=" ".join(w.text for w in window),
                    words=window,
                )
            )
            if start + max_words >= len(page.words):
                break  # the rest is already inside this window
    return chunks
