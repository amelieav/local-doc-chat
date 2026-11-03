"""Vector storage and nearest-neighbour search."""

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Protocol
from uuid import UUID

import sqlite_vec
from pydantic import BaseModel, ConfigDict


class VectorDimensionError(Exception):
    """A vector's length does not match the store's dimensions."""


class VectorHit(BaseModel):
    """A chunk found by search. Smaller distance means closer."""

    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    distance: float


class VectorStore(Protocol):
    """Where chunk vectors live. Swappable behind this interface."""

    def add(self, chunk_ids: Sequence[UUID], vectors: Sequence[Sequence[float]]) -> None: ...

    def search(self, vector: Sequence[float], k: int) -> list[VectorHit]: ...

    def delete(self, chunk_ids: Sequence[UUID]) -> None: ...


class SqliteVecStore:
    """VectorStore using a sqlite-vec table with cosine distance.

    The dimensions are fixed on first use. Switching to an embedding model with a different size
    needs a new database, because the old vectors are not comparable.
    """

    def __init__(self, db_path: Path, dimensions: int) -> None:
        if dimensions < 1:
            msg = "dimensions must be at least 1"
            raise ValueError(msg)
        self._db_path = db_path
        self._dimensions = dimensions
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute("CREATE TABLE IF NOT EXISTS vector_meta (dimensions INTEGER NOT NULL)")
            row = conn.execute("SELECT dimensions FROM vector_meta").fetchone()
            if row is None:
                conn.execute("INSERT INTO vector_meta VALUES (?)", (dimensions,))
            elif row[0] != dimensions:
                msg = f"Store holds {row[0]}-dimension vectors, not {dimensions}"
                raise VectorDimensionError(msg)
            # dimensions is an int checked above, so formatting it into the DDL is safe.
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0("
                f"chunk_id TEXT PRIMARY KEY, embedding FLOAT[{dimensions}] distance_metric=cosine)"
            )

    def add(self, chunk_ids: Sequence[UUID], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunk_ids) != len(vectors):
            msg = f"Got {len(chunk_ids)} ids but {len(vectors)} vectors"
            raise ValueError(msg)
        rows = [(str(i), self._serialize(v)) for i, v in zip(chunk_ids, vectors, strict=True)]
        with closing(self._connect()) as conn, conn:
            conn.executemany("INSERT INTO chunk_vectors(chunk_id, embedding) VALUES (?, ?)", rows)

    def search(self, vector: Sequence[float], k: int) -> list[VectorHit]:
        if k < 1:
            msg = "k must be at least 1"
            raise ValueError(msg)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT chunk_id, distance FROM chunk_vectors "
                "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                (self._serialize(vector), k),
            ).fetchall()
        return [VectorHit(chunk_id=UUID(r[0]), distance=r[1]) for r in rows]

    def delete(self, chunk_ids: Sequence[UUID]) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executemany(
                "DELETE FROM chunk_vectors WHERE chunk_id = ?", [(str(i),) for i in chunk_ids]
            )

    def _serialize(self, vector: Sequence[float]) -> bytes:
        if len(vector) != self._dimensions:
            msg = f"Expected a {self._dimensions}-dimension vector, got {len(vector)}"
            raise VectorDimensionError(msg)
        return sqlite_vec.serialize_float32(list(vector))  # type: ignore[no-any-return]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn
