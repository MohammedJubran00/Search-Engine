"""Authenticated HTTP routes for private document management."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
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
from src.search_engine.schemas.document import DocumentResponse
from src.search_engine.services.document_service import (
    DocumentNotFoundError,
    DocumentPersistenceError,
    DocumentProcessingError,
    DocumentService,
    InvalidUploadError,
)

router = APIRouter()


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
    return DocumentResponse.model_validate(result.document)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    documents = await DocumentService(db).list_for_user(user.id)
    return [DocumentResponse.model_validate(document) for document in documents]


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
