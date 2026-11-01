"""Authenticated HTTP routes for private document management."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.search_engine.database.database import get_db
from src.search_engine.deps import get_current_user
from src.search_engine.models.user import User
from src.search_engine.rag.parsers import DocumentParseError
from src.search_engine.rag.storage import (
    EmptyUploadError,
    FileTooLargeError,
    StorageOperationError,
)
from src.search_engine.schemas.document import DocumentPage, DocumentResponse, IndexingJobResponse
from src.search_engine.services.document_service import (
    DocumentNotFoundError,
    DocumentPersistenceError,
    DocumentProcessingError,
    DocumentService,
    InvalidUploadError,
)
from src.search_engine.repositories.document_index_repository import (
    ConcurrentDocumentIndexingError,
)
from src.search_engine.services.document_indexing_service import (
    DocumentIndexingError,
    DocumentIndexingNotFoundError,
    DocumentIndexingQuotaError,
    DocumentIndexingService,
)
from src.search_engine.services.observability_service import observability
from src.search_engine.services.indexing_queue_service import IndexingQueueService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: Annotated[UploadFile, File()],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Securely store and parse one supported document for the current user."""
    try:
        result = await DocumentService(db).upload(user_id=user.id, upload=file)
    except FileTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc))
    except InvalidUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from None
    except (DocumentParseError, EmptyUploadError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except (
        StorageOperationError,
        DocumentPersistenceError,
        DocumentProcessingError,
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to store the document safely.",
        ) from None
    finally:
        await file.close()
    if result.document.indexing_status not in {'completed', 'processing', 'queued'}:
        await IndexingQueueService(db).enqueue(document_id=result.document.id, user_id=user.id)
    await db.commit()
    refreshed = await DocumentService(db).get_for_user(
        document_id=result.document.id, user_id=user.id
    )
    return DocumentResponse.model_validate(refreshed)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    documents = await DocumentService(db).list_for_user(user.id)
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get("/page", response_model=DocumentPage)
async def page_documents(
    search: str | None = Query(default=None, max_length=255),
    indexing_status: str | None = Query(default=None),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> DocumentPage:
    if indexing_status not in {None, "queued", "processing", "completed", "failed"}:
        raise HTTPException(status_code=400, detail="Invalid indexing status.")
    items, total = await DocumentService(db).page_for_user(
        user.id, search=search, status=indexing_status, limit=limit, offset=offset
    )
    return DocumentPage(
        items=[DocumentResponse.model_validate(item) for item in items],
        total=total, limit=limit, offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    try:
        document = await DocumentService(db).get_for_user(
            document_id=document_id,
            user_id=user.id,
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return DocumentResponse.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await DocumentService(db).delete_for_user(
            document_id=document_id,
            user_id=user.id,
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    except (StorageOperationError, DocumentPersistenceError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete the document safely.",
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/index", response_model=DocumentResponse)
async def index_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Compatibility endpoint: enqueue or retry indexing without blocking HTTP."""
    documents = DocumentService(db)
    try:
        document = await documents.get_for_user(
            document_id=document_id,
            user_id=user.id,
        )
        if document.indexing_status == "completed":
            return DocumentResponse.model_validate(document)
        await IndexingQueueService(db).enqueue(document_id=document_id, user_id=user.id)
        await db.commit()
        refreshed = await documents.get_for_user(
            document_id=document_id,
            user_id=user.id,
        )
        return DocumentResponse.model_validate(refreshed)
    except (DocumentNotFoundError, DocumentIndexingNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from None
    except ConcurrentDocumentIndexingError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document indexing is already in progress.",
        ) from None
    except DocumentIndexingQuotaError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini embedding quota or capacity is currently unavailable.",
        ) from None
    except DocumentIndexingError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to prepare the document for AI questions.",
        ) from None
    except Exception:
        logger.exception("Unable to enqueue document %s for indexing", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to queue the document for indexing.",
        ) from None


@router.get("/{document_id}/index-job", response_model=IndexingJobResponse | None)
async def get_indexing_job(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IndexingJobResponse | None:
    try:
        await DocumentService(db).get_for_user(document_id=document_id, user_id=user.id)
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found.") from None
    job = await IndexingQueueService(db).latest(document_id=document_id, user_id=user.id)
    return IndexingJobResponse.model_validate(job) if job else None
