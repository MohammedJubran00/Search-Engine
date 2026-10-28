"""Secure upload, parsing, ownership, and deletion orchestration.

Why it exists: coordinating private files with database records crosses the
repository and parser boundaries and must not be duplicated in HTTP routes.
Parsing and filesystem work are sent to worker threads to protect the event
loop. No chunking, embedding, or retrieval occurs here.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.core.config import settings
from src.search_engine.models.document import Document
from src.search_engine.rag.contracts import ParsedDocument
from src.search_engine.rag.parsers import (
    DOCX_CONTENT_TYPE,
    PDF_CONTENT_TYPE,
    TXT_CONTENT_TYPE,
    DocumentParseError,
    RagDocumentParser,
)
from src.search_engine.rag.storage import (
    DocumentStorage,
    EmptyUploadError,
    FileTooLargeError,
    StorageOperationError,
)
from src.search_engine.repositories.document_repository import DocumentRepository

logger = logging.getLogger(__name__)

_UPLOAD_TYPES = {
    ".pdf": PDF_CONTENT_TYPE,
    ".docx": DOCX_CONTENT_TYPE,
    ".txt": TXT_CONTENT_TYPE,
}


class InvalidUploadError(ValueError):
    """Raised when upload metadata is unsafe or unsupported."""


class DocumentNotFoundError(LookupError):
    """Raised for missing and foreign documents without leaking ownership."""


class DocumentPersistenceError(RuntimeError):
    """Raised when a database operation fails after safe cleanup."""


class DocumentProcessingError(RuntimeError):
    """Raised after cleaning up an unexpected processing failure."""


@dataclass(frozen=True, slots=True)
class UploadResult:
    """Persisted metadata plus extracted text for internal/future phases."""

    document: Document
    parsed: ParsedDocument


class DocumentService:
    """Authenticated document use cases for one database session."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        repository: DocumentRepository | None = None,
        storage: DocumentStorage | None = None,
        parser: RagDocumentParser | None = None,
    ) -> None:
        self._session = session
        self._documents = repository or DocumentRepository(session)
        self._storage = storage or DocumentStorage(settings.rag_storage_dir)
        self._parser = parser or RagDocumentParser(
            max_docx_uncompressed_bytes=settings.rag_max_docx_uncompressed_bytes,
            pdf_boilerplate_min_pages=settings.rag_pdf_boilerplate_min_pages,
            pdf_boilerplate_page_ratio=settings.rag_pdf_boilerplate_page_ratio,
            pdf_boilerplate_margin_ratio=settings.rag_pdf_boilerplate_margin_ratio,
            pdf_boilerplate_max_line_characters=(
                settings.rag_pdf_boilerplate_max_line_characters
            ),
        )

    async def upload(self, *, user_id: uuid.UUID, upload: UploadFile) -> UploadResult:
        filename, extension, content_type = _validate_upload_metadata(upload)
        if upload.size is not None and upload.size > settings.rag_max_upload_bytes:
            raise FileTooLargeError(
                f"Document exceeds the {settings.rag_max_upload_bytes}-byte upload limit."
            )

        target = self._storage.new_target(extension)
        committed = False
        try:
            file_size = await asyncio.to_thread(
                self._storage.write_limited,
                upload.file,
                target,
                settings.rag_max_upload_bytes,
            )
            document = await self._documents.create(
                user_id=user_id,
                original_filename=filename,
                storage_path=target.reference,
                content_type=content_type,
                file_size=file_size,
            )
            await self._documents.set_status(document, "processing")
            parsed = await asyncio.to_thread(
                self._parser.parse,
                target.temporary_path,
                content_type,
            )
            await asyncio.to_thread(self._storage.promote, target)
            await self._documents.set_status(document, "completed")
            await self._session.commit()
            committed = True
            return UploadResult(document=document, parsed=parsed)
        except (DocumentParseError, EmptyUploadError, FileTooLargeError, InvalidUploadError):
            await self._session.rollback()
            raise
        except StorageOperationError:
            await self._session.rollback()
            raise
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise DocumentPersistenceError("Unable to save document metadata.") from exc
        except Exception as exc:
            await self._session.rollback()
            raise DocumentProcessingError("Unable to process the document.") from exc
        finally:
            self._storage.remove_path(target.temporary_path)
            if not committed:
                self._storage.remove_path(target.final_path)

    async def list_for_user(self, user_id: uuid.UUID) -> list[Document]:
        return await self._documents.list_for_user(user_id)

    async def get_for_user(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Document:
        document = await self._documents.get_by_id_for_user(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError
        return document

    async def delete_for_user(
        self,
        *,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        document = await self.get_for_user(
            document_id=document_id,
            user_id=user_id,
        )
        quarantined = await asyncio.to_thread(
            self._storage.quarantine,
            document.storage_path,
        )
        try:
            await self._documents.delete(document)
            await self._session.commit()
        except SQLAlchemyError as exc:
            await self._session.rollback()
            try:
                await asyncio.to_thread(self._storage.restore, quarantined)
            except OSError:
                logger.exception("Failed to restore document after database rollback")
            raise DocumentPersistenceError("Unable to delete document metadata.") from exc

        if quarantined is not None:
            await asyncio.to_thread(self._storage.remove_path, quarantined[1])


def _validate_upload_metadata(upload: UploadFile) -> tuple[str, str, str]:
    filename = (upload.filename or "").strip()
    if not filename or "\x00" in filename:
        raise InvalidUploadError("A safe document filename is required.")
    if len(filename) > 255:
        raise InvalidUploadError("Document filename is too long.")
    if (
        PurePosixPath(filename).name != filename
        or PureWindowsPath(filename).name != filename
    ):
        raise InvalidUploadError("Document filename must not contain a path.")

    extension = Path(filename).suffix.lower()
    expected_content_type = _UPLOAD_TYPES.get(extension)
    if expected_content_type is None:
        raise InvalidUploadError("Only PDF, DOCX, and TXT documents are supported.")
    actual_content_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
    if actual_content_type != expected_content_type:
        raise InvalidUploadError("Filename extension and content type do not match.")
    return filename, extension, expected_content_type
