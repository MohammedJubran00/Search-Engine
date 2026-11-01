import { useCallback, useEffect, useState } from 'react'
import {
  deleteDocument,
  fetchDocument,
  fetchDocuments,
  formatDocumentBytes,
} from '../api/documents'
import './DocumentPanel.css'

const MAX_DOCUMENT_SELECTION = Number.parseInt(
  import.meta.env.VITE_RAG_CHAT_MAX_DOCUMENT_SELECTION || '10',
  10,
)

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export default function DocumentPanel({
  documents,
  onDocumentsChange,
  selectionEnabled,
  selectedDocumentIds,
  onSelectionChange,
}) {
  const [selectedDocument, setSelectedDocument] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [detailsLoadingId, setDetailsLoadingId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [error, setError] = useState('')
  const [isExpanded, setIsExpanded] = useState(true)

  const loadDocuments = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      onDocumentsChange(await fetchDocuments())
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not load documents.')
    } finally {
      setIsLoading(false)
    }
  }, [onDocumentsChange])

  useEffect(() => {
    let cancelled = false

    fetchDocuments()
      .then((items) => {
        if (!cancelled) onDocumentsChange(items)
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : 'Could not load documents.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [onDocumentsChange])

  useEffect(() => {
    const existing = new Set(documents.map((item) => item.id))
    const validSelection = selectedDocumentIds.filter((id) => existing.has(id))
    if (validSelection.length !== selectedDocumentIds.length) {
      onSelectionChange(validSelection)
    }
  }, [documents, onSelectionChange, selectedDocumentIds])

  async function handleView(documentId) {
    setDetailsLoadingId(documentId)
    setError('')
    try {
      setSelectedDocument(await fetchDocument(documentId))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not load details.')
    } finally {
      setDetailsLoadingId(null)
    }
  }

  async function handleDelete(document) {
    const confirmed = await confirmAction(`Delete “${document.original_filename}”?`)
    if (!confirmed || deletingId) return

    setDeletingId(document.id)
    setError('')
    try {
      await deleteDocument(document.id)
      onDocumentsChange(documents.filter((item) => item.id !== document.id))
      if (selectedDocument?.id === document.id) setSelectedDocument(null)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not delete document.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="documents" aria-labelledby="documents-title">
      <div className="documents__header">
        <button
          type="button"
          className="documents__toggle"
          aria-expanded={isExpanded}
          onClick={() => setIsExpanded((current) => !current)}
        >
          <span>
            <strong id="documents-title">Documents</strong>
            <small>{documents.length} uploaded</small>
          </span>
          <span aria-hidden="true">{isExpanded ? '−' : '+'}</span>
        </button>
        <div className="documents__header-actions">
          <button
            type="button"
            className="documents__secondary"
            onClick={loadDocuments}
            disabled={isLoading}
          >
            {isLoading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {isExpanded ? (
        <div className="documents__body">
          {error ? <p className="documents__message documents__message--error">{error}</p> : null}

          {isLoading ? (
            <p className="documents__state">Loading documents…</p>
          ) : documents.length === 0 ? (
            <p className="documents__state">No documents yet. Upload one, then index it before Document Chat.</p>
          ) : (
            <ul className="documents__list">
              {documents.map((document) => (
                <li key={document.id} className="documents__item">
                  {selectionEnabled ? (
                    <input
                      className="documents__context-check"
                      type="checkbox"
                      aria-label={`Use ${document.original_filename} in Document Chat`}
                      checked={selectedDocumentIds.includes(document.id)}
                      disabled={
                        document.indexing_status !== 'completed' ||
                        (!selectedDocumentIds.includes(document.id) &&
                          selectedDocumentIds.length >= MAX_DOCUMENT_SELECTION)
                      }
                      onChange={(event) => {
                        onSelectionChange(
                          event.target.checked
                            ? [...selectedDocumentIds, document.id]
                            : selectedDocumentIds.filter((id) => id !== document.id),
                        )
                      }}
                    />
                  ) : null}
                  <div className="documents__item-main">
                    <strong title={document.original_filename}>{document.original_filename}</strong>
                    <span>
                      {formatDocumentBytes(document.file_size)} · {formatDate(document.created_at)}
                    </span>
                  </div>
                  <span className={`documents__status documents__status--${document.indexing_status}`}>
                    {document.indexing_status === 'completed'
                      ? 'indexed'
                      : document.indexing_status.replace('_', ' ')}
                  </span>
                  <div className="documents__item-actions">
                    <button
                      type="button"
                      onClick={() => handleView(document.id)}
                      disabled={detailsLoadingId === document.id}
                    >
                      {detailsLoadingId === document.id ? 'Loading…' : 'Details'}
                    </button>
                    <button
                      type="button"
                      className="documents__delete"
                      onClick={() => handleDelete(document)}
                      disabled={deletingId === document.id}
                    >
                      {deletingId === document.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {selectedDocument ? (
            <aside className="documents__details" aria-label="Document metadata">
              <div>
                <strong>{selectedDocument.original_filename}</strong>
                <span>{selectedDocument.content_type}</span>
              </div>
              <dl>
                <div>
                  <dt>Size</dt>
                  <dd>{formatDocumentBytes(selectedDocument.file_size)}</dd>
                </div>
                <div>
                  <dt>Uploaded</dt>
                  <dd>{formatDate(selectedDocument.created_at)}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{selectedDocument.processing_status}</dd>
                </div>
                <div>
                  <dt>Index</dt>
                  <dd>{selectedDocument.indexing_status?.replace('_', ' ')}</dd>
                </div>
              </dl>
              <button type="button" onClick={() => setSelectedDocument(null)}>
                Close details
              </button>
            </aside>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
import { confirmAction } from './AppDialog'
