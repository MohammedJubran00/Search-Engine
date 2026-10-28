"""Phase 4 indexing lifecycle, atomic replacement, and ownership tests."""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.search_engine.models.document import Document
from src.search_engine.rag.chunking import RagTextChunker
from src.search_engine.rag.contracts import ParsedDocument, TextChunk
from src.search_engine.rag.embeddings import EmbeddingRateLimitError
from src.search_engine.rag.parsers import TXT_CONTENT_TYPE, RagDocumentParser
from src.search_engine.rag.storage import DocumentStorage
from src.search_engine.repositories.document_index_repository import (
    ConcurrentDocumentIndexingError,
    IndexingClaim,
    InvalidIndexPayloadError,
    prepare_document_chunks,
)
from src.search_engine.services.document_indexing_service import (
    DocumentIndexingError,
    DocumentIndexingNotFoundError,
    DocumentIndexingService,
    EmptyDocumentIndexError,
)

DIMENSIONS = 1_536


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeIndexRepository:
    def __init__(self, document: Document) -> None:
        self.document = document
        self.status = "not_indexed"
        self.generation = 0
        self.error_message: str | None = None
        self.chunks: list[TextChunk] = []
        self.embeddings: list[list[float]] = []
        self.fail_replace = False

    async def claim(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        supersede_processing: bool = False,
    ) -> IndexingClaim | None:
        if document_id != self.document.id or user_id != self.document.user_id:
            return None
        if self.status == "processing" and not supersede_processing:
            raise ConcurrentDocumentIndexingError
        self.generation += 1
        self.status = "processing"
        self.error_message = None
        return IndexingClaim(self.document, self.generation)

    async def replace(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        generation: int,
        chunks: list[TextChunk],
        embeddings: list[list[float]],
    ) -> int:
        if self.fail_replace:
            raise RuntimeError("forced database failure")
        assert document_id == self.document.id
        assert user_id == self.document.user_id
        assert generation == self.generation
        self.chunks = list(chunks)
        self.embeddings = [list(vector) for vector in embeddings]
        self.status = "completed"
        return len(chunks)

    async def mark_failed(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        generation: int,
        error_message: str,
    ) -> bool:
        if (
            document_id != self.document.id
            or user_id != self.document.user_id
            or generation != self.generation
            or self.status != "processing"
        ):
            return False
        self.status = "failed"
        self.error_message = error_message
        return True


class FakeEmbeddingProvider:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[list[str]] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.error:
            raise self.error
        return [[1.0] + [0.0] * (DIMENSIONS - 1) for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [1.0] + [0.0] * (DIMENSIONS - 1)


class EmptyParser:
    def parse(self, path: Path, content_type: str) -> ParsedDocument:
        return ParsedDocument(text="")


def _document(tmp_path: Path) -> Document:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    reference = "stored.txt"
    (tmp_path / reference).write_text(
        "Heading\n\nEnglish text and نص عربي dated 2026-10-27. " * 12,
        encoding="utf-8",
    )
    now = datetime.now(timezone.utc)
    return Document(
        id=document_id,
        user_id=user_id,
        original_filename="report.txt",
        storage_path=reference,
        content_type=TXT_CONTENT_TYPE,
        file_size=(tmp_path / reference).stat().st_size,
        processing_status="completed",
        created_at=now,
        updated_at=now,
    )


def _service(
    tmp_path: Path,
    document: Document,
    repository: FakeIndexRepository,
    embeddings: FakeEmbeddingProvider,
    *,
    parser: object | None = None,
) -> tuple[DocumentIndexingService, FakeSession]:
    session = FakeSession()
    service = DocumentIndexingService(
        session,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        storage=DocumentStorage(tmp_path),
        parser=parser  # type: ignore[arg-type]
        or RagDocumentParser(max_docx_uncompressed_bytes=1024 * 1024),
        chunker=RagTextChunker(chunk_size=100, chunk_overlap=20),
        embeddings=embeddings,
    )
    return service, session


def test_indexing_preserves_chunk_order_metadata_and_lifecycle(tmp_path: Path) -> None:
    document = _document(tmp_path)
    repository = FakeIndexRepository(document)
    embeddings = FakeEmbeddingProvider()
    service, session = _service(tmp_path, document, repository, embeddings)

    result = asyncio.run(
        service.index(document_id=document.id, user_id=document.user_id)
    )

    assert result.generation == 1
    assert result.chunk_count == len(repository.chunks) > 1
    assert repository.status == "completed"
    assert [chunk.index for chunk in repository.chunks] == list(
        range(result.chunk_count)
    )
    assert all("page_number" not in chunk.metadata for chunk in repository.chunks)
    assert all("char_start" in chunk.metadata for chunk in repository.chunks)
    assert len(repository.embeddings) == result.chunk_count
    assert session.commits == 2


def test_reindex_replaces_instead_of_accumulating_duplicates(tmp_path: Path) -> None:
    document = _document(tmp_path)
    repository = FakeIndexRepository(document)
    service, _ = _service(
        tmp_path,
        document,
        repository,
        FakeEmbeddingProvider(),
    )

    first = asyncio.run(service.index(document_id=document.id, user_id=document.user_id))
    first_indexes = [chunk.index for chunk in repository.chunks]
    second = asyncio.run(service.index(document_id=document.id, user_id=document.user_id))

    assert first.chunk_count == second.chunk_count == len(repository.chunks)
    assert second.generation == 2
    assert [chunk.index for chunk in repository.chunks] == first_indexes


@pytest.mark.parametrize(
    "failure",
    [EmbeddingRateLimitError("429"), RuntimeError("upstream failure")],
)
def test_embedding_failure_preserves_previous_valid_index(
    tmp_path: Path,
    failure: Exception,
) -> None:
    document = _document(tmp_path)
    repository = FakeIndexRepository(document)
    previous = TextChunk(
        document_id=document.id,
        user_id=document.user_id,
        index=0,
        text="previous valid chunk",
    )
    repository.chunks = [previous]
    service, session = _service(
        tmp_path,
        document,
        repository,
        FakeEmbeddingProvider(error=failure),
    )

    with pytest.raises(DocumentIndexingError):
        asyncio.run(service.index(document_id=document.id, user_id=document.user_id))

    assert repository.chunks == [previous]
    assert repository.status == "failed"
    assert repository.error_message == "Document indexing failed."
    assert session.rollbacks == 1


def test_database_replacement_failure_preserves_previous_index(tmp_path: Path) -> None:
    document = _document(tmp_path)
    repository = FakeIndexRepository(document)
    previous = TextChunk(document.id, document.user_id, 0, "previous")
    repository.chunks = [previous]
    repository.fail_replace = True
    service, session = _service(
        tmp_path,
        document,
        repository,
        FakeEmbeddingProvider(),
    )

    with pytest.raises(DocumentIndexingError, match="Unable to index"):
        asyncio.run(service.index(document_id=document.id, user_id=document.user_id))

    assert repository.chunks == [previous]
    assert repository.status == "failed"
    assert session.rollbacks == 1


def test_cross_user_access_is_rejected_before_file_or_embedding_work(
    tmp_path: Path,
) -> None:
    document = _document(tmp_path)
    repository = FakeIndexRepository(document)
    embeddings = FakeEmbeddingProvider()
    service, session = _service(tmp_path, document, repository, embeddings)

    with pytest.raises(DocumentIndexingNotFoundError):
        asyncio.run(service.index(document_id=document.id, user_id=uuid.uuid4()))

    assert embeddings.calls == []
    assert repository.status == "not_indexed"
    assert session.rollbacks == 1


def test_empty_parsed_document_fails_explicitly_without_replacing_chunks(
    tmp_path: Path,
) -> None:
    document = _document(tmp_path)
    repository = FakeIndexRepository(document)
    service, _ = _service(
        tmp_path,
        document,
        repository,
        FakeEmbeddingProvider(),
        parser=EmptyParser(),
    )

    with pytest.raises(EmptyDocumentIndexError):
        asyncio.run(service.index(document_id=document.id, user_id=document.user_id))

    assert repository.status == "failed"
    assert repository.chunks == []


def test_concurrent_indexing_claim_is_rejected(tmp_path: Path) -> None:
    document = _document(tmp_path)
    repository = FakeIndexRepository(document)
    repository.status = "processing"
    service, _ = _service(
        tmp_path,
        document,
        repository,
        FakeEmbeddingProvider(),
    )

    with pytest.raises(ConcurrentDocumentIndexingError):
        asyncio.run(service.index(document_id=document.id, user_id=document.user_id))


def test_explicit_recovery_supersedes_an_abandoned_generation(tmp_path: Path) -> None:
    document = _document(tmp_path)
    repository = FakeIndexRepository(document)
    repository.status = "processing"
    repository.generation = 4
    service, _ = _service(
        tmp_path,
        document,
        repository,
        FakeEmbeddingProvider(),
    )

    result = asyncio.run(
        service.index(
            document_id=document.id,
            user_id=document.user_id,
            supersede_processing=True,
        )
    )

    assert result.generation == 5
    assert repository.status == "completed"


def test_persistence_payload_validates_dimensions_order_ownership_and_metadata() -> None:
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    chunks = [
        TextChunk(
            document_id=document_id,
            user_id=user_id,
            index=0,
            text="citation text",
            metadata={"page_number": 2, "char_start": 10, "char_end": 23},
        )
    ]
    vector = [1.0] + [0.0] * (DIMENSIONS - 1)

    rows = prepare_document_chunks(
        document_id=document_id,
        user_id=user_id,
        chunks=chunks,
        embeddings=[vector],
    )

    assert len(rows) == 1
    assert rows[0].chunk_index == 0
    assert rows[0].page_number == 2
    assert rows[0].char_start == 10
    assert rows[0].char_end == 23
    assert len(rows[0].embedding or []) == DIMENSIONS

    with pytest.raises(InvalidIndexPayloadError, match="exactly one embedding"):
        prepare_document_chunks(
            document_id=document_id,
            user_id=user_id,
            chunks=chunks,
            embeddings=[],
        )
    with pytest.raises(ValueError, match="1536 dimensions"):
        prepare_document_chunks(
            document_id=document_id,
            user_id=user_id,
            chunks=chunks,
            embeddings=[[1.0]],
        )
    with pytest.raises(InvalidIndexPayloadError, match="zero-based"):
        prepare_document_chunks(
            document_id=document_id,
            user_id=user_id,
            chunks=[
                TextChunk(document_id, user_id, 1, "wrong index"),
            ],
            embeddings=[vector],
        )
    with pytest.raises(InvalidIndexPayloadError, match="ownership"):
        prepare_document_chunks(
            document_id=document_id,
            user_id=user_id,
            chunks=[TextChunk(document_id, uuid.uuid4(), 0, "foreign")],
            embeddings=[vector],
        )
