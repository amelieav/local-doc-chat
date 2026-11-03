from pathlib import Path
from uuid import UUID, uuid4

import pytest

from local_doc_chat.store.vectors import SqliteVecStore, VectorDimensionError


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "vectors.sqlite"


@pytest.fixture
def store(db: Path) -> SqliteVecStore:
    return SqliteVecStore(db, dimensions=2)


def add_three(store: SqliteVecStore) -> tuple[UUID, UUID, UUID]:
    east, north, northeast = uuid4(), uuid4(), uuid4()
    store.add([east, north, northeast], [[1, 0], [0, 1], [1, 1]])
    return east, north, northeast


def test_search_returns_nearest_first(store: SqliteVecStore) -> None:
    east, north, northeast = add_three(store)

    hits = store.search([1, 0.1], k=3)

    assert [h.chunk_id for h in hits] == [east, northeast, north]
    assert hits[0].distance < hits[1].distance < hits[2].distance


def test_search_limits_to_k(store: SqliteVecStore) -> None:
    east, _, _ = add_three(store)

    assert [h.chunk_id for h in store.search([1, 0], k=1)] == [east]


def test_search_empty_store(store: SqliteVecStore) -> None:
    assert store.search([1, 0], k=5) == []


def test_delete_removes_vectors(store: SqliteVecStore) -> None:
    east, north, northeast = add_three(store)

    store.delete([east, northeast])

    assert [h.chunk_id for h in store.search([1, 0], k=5)] == [north]


def test_rejects_wrong_dimensions(store: SqliteVecStore) -> None:
    with pytest.raises(VectorDimensionError):
        store.add([uuid4()], [[1, 2, 3]])
    with pytest.raises(VectorDimensionError):
        store.search([1, 2, 3], k=1)


def test_rejects_mismatched_ids_and_vectors(store: SqliteVecStore) -> None:
    with pytest.raises(ValueError, match="ids"):
        store.add([uuid4()], [[1, 0], [0, 1]])


def test_rejects_bad_k(store: SqliteVecStore) -> None:
    with pytest.raises(ValueError, match="k must"):
        store.search([1, 0], k=0)


def test_vectors_survive_reopening_but_dimensions_must_match(db: Path) -> None:
    first = SqliteVecStore(db, dimensions=2)
    east, _, _ = add_three(first)

    reopened = SqliteVecStore(db, dimensions=2)

    assert reopened.search([1, 0], k=1)[0].chunk_id == east
    with pytest.raises(VectorDimensionError):
        SqliteVecStore(db, dimensions=3)
