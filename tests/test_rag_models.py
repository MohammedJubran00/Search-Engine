"""Focused metadata tests for the Phase 1 RAG persistence models."""

from pgvector.sqlalchemy import Vector

from src.search_engine.core.config import settings
from src.search_engine.database.database import Base
from src.search_engine.models import Document, DocumentChunk, DocumentIndexState


def test_rag_tables_are_registered_in_shared_metadata() -> None:
    assert Document.__table__ is Base.metadata.tables["documents"]
    assert DocumentChunk.__table__ is Base.metadata.tables["document_chunks"]
    assert DocumentIndexState.__table__ is Base.metadata.tables["document_index_states"]


def test_document_chunk_embedding_matches_configured_dimension() -> None:
    embedding_type = DocumentChunk.__table__.c.embedding.type

    assert isinstance(embedding_type, Vector)
    assert embedding_type.dim == settings.rag_embedding_dimensions == 1_536
    assert DocumentChunk.__table__.c.embedding.nullable is True


def test_gemini_retrieval_embedding_configuration() -> None:
    assert settings.rag_embedding_model == "models/gemini-embedding-001"
    assert settings.rag_embedding_document_task_type == "RETRIEVAL_DOCUMENT"
    assert settings.rag_embedding_query_task_type == "RETRIEVAL_QUERY"
    assert settings.rag_embedding_normalize is True
    assert settings.rag_embedding_batch_size == 100
    assert settings.rag_embedding_max_concurrency > 0
    assert settings.rag_embedding_max_retries >= 0


def test_document_chunk_order_is_unique_per_document() -> None:
    constraint_names = {
        constraint.name for constraint in DocumentChunk.__table__.constraints
    }

    assert "uq_document_chunks_document_id_chunk_index" in constraint_names


def test_document_ownership_is_indexed_and_cascades() -> None:
    user_id = Document.__table__.c.user_id
    foreign_key = next(iter(user_id.foreign_keys))

    assert user_id.index is True
    assert foreign_key.target_fullname == "users.id"
    assert foreign_key.ondelete == "CASCADE"


def test_document_chunks_cascade_with_parent_document() -> None:
    document_id = DocumentChunk.__table__.c.document_id
    foreign_key = next(iter(document_id.foreign_keys))

    assert foreign_key.target_fullname == "documents.id"
    assert foreign_key.ondelete == "CASCADE"


def test_index_state_cascades_and_has_separate_lifecycle_constraints() -> None:
    document_id = DocumentIndexState.__table__.c.document_id
    foreign_key = next(iter(document_id.foreign_keys))
    constraint_names = {
        constraint.name for constraint in DocumentIndexState.__table__.constraints
    }

    assert foreign_key.target_fullname == "documents.id"
    assert foreign_key.ondelete == "CASCADE"
    assert "ck_document_index_states_status" in constraint_names
    assert "ck_document_index_states_generation_nonnegative" in constraint_names


def test_chunk_character_offsets_support_existing_rows_and_validate_ranges() -> None:
    table = DocumentChunk.__table__
    constraint_names = {constraint.name for constraint in table.constraints}

    assert table.c.char_start.nullable is True
    assert table.c.char_end.nullable is True
    assert "ck_document_chunks_character_range" in constraint_names
