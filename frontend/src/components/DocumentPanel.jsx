import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteDocument,
  fetchDocument,
  fetchDocuments,
  MAX_DOCUMENT_BYTES,
  SUPPORTED_DOCUMENT_EXTENSIONS,
  uploadDocument,
} from '../api/documents'
import './DocumentPanel.css'

const FILE_ACCEPT =
  '.pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain'

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return 'Unknown size'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function validateFile(file) {
  if (!file) return 'Choose a document first.'
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (!extension || !SUPPORTED_DOCUMENT_EXTENSIONS.has(extension)) {
    return 'Choose a PDF, DOCX, or TXT document.'
  }
  if (file.size === 0) return 'The selected document is empty.'
  if (file.size > MAX_DOCUMENT_BYTES) {
    return `The document must be ${formatBytes(MAX_DOCUMENT_BYTES)} or smaller.`
  }
  return ''
}

export default function DocumentPanel() {
  const [documents, setDocuments] = useState([])
  const [selectedFile, setSelectedFile] = useState(null)
  const [selectedDocument, setSelectedDocument] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isUploading, setIsUploading] = useState(false)
  const [detailsLoadingId, setDetailsLoadingId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [isExpanded, setIsExpanded] = useState(true)
  const inputRef = useRef(null)

  const loadDocuments = useCallback(async () => {
    setIsLoading(true)
    setError('')
    try {
      setDocuments(await fetchDocuments())
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not load documents.')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    fetchDocuments()
      .then((items) => {
        if (!cancelled) setDocuments(items)
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
  }, [])

  function handleFileChange(event) {
    const file = event.target.files?.[0] || null
    setNotice('')
    setError(validateFile(file))
    setSelectedFile(file)
  }

  async function handleUpload(event) {
    event.preventDefault()
    const validationError = validateFile(selectedFile)
    if (validationError || isUploading) {
      setError(validationError)
      return
    }

    setIsUploading(true)
    setError('')
    setNotice('Uploading and validating document…')
    try {
      const uploaded = await uploadDocument(selectedFile)
      setDocuments((current) => [uploaded, ...current.filter((item) => item.id !== uploaded.id)])
      setSelectedDocument(uploaded)
      setSelectedFile(null)
      if (inputRef.current) inputRef.current.value = ''
      setNotice('Document uploaded and parsed successfully.')
    } catch (requestError) {
      setNotice('')
      setError(requestError instanceof Error ? requestError.message : 'Upload failed.')
    } finally {
      setIsUploading(false)
    }
  }

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
    const confirmed = window.confirm(`Delete “${document.original_filename}”?`)
    if (!confirmed || deletingId) return

    setDeletingId(document.id)
    setError('')
    setNotice('')
    try {
      await deleteDocument(document.id)
      setDocuments((current) => current.filter((item) => item.id !== document.id))
      if (selectedDocument?.id === document.id) setSelectedDocument(null)
      setNotice('Document deleted.')
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
            disabled={isLoading || isUploading}
          >
            {isLoading ? 'Refreshing…' : 'Refresh'}
          </button>
          <label className="documents__choose">
            Choose document
            <input
              ref={inputRef}
              type="file"
              accept={FILE_ACCEPT}
              onChange={handleFileChange}
              disabled={isUploading}
            />
          </label>
        </div>
      </div>

      {isExpanded ? (
        <div className="documents__body">
          <form className="documents__upload" onSubmit={handleUpload}>
            <div className="documents__selection">
              <span>{selectedFile ? selectedFile.name : 'No document selected'}</span>
              <small>PDF, DOCX, or TXT · up to {formatBytes(MAX_DOCUMENT_BYTES)}</small>
            </div>
            <button
              type="submit"
              className="documents__upload-button"
              disabled={!selectedFile || isUploading}
            >
              {isUploading ? 'Uploading…' : 'Upload document'}
            </button>
          </form>

          {error ? <p className="documents__message documents__message--error">{error}</p> : null}
          {notice ? (
            <p className="documents__message" role="status">
              {isUploading ? <span className="documents__spinner" aria-hidden="true" /> : null}
              {notice}
            </p>
          ) : null}

          {isLoading ? (
            <p className="documents__state">Loading documents…</p>
          ) : documents.length === 0 ? (
            <p className="documents__state">No documents yet. Upload one to test parsing.</p>
          ) : (
            <ul className="documents__list">
              {documents.map((document) => (
                <li key={document.id} className="documents__item">
                  <div className="documents__item-main">
                    <strong title={document.original_filename}>{document.original_filename}</strong>
                    <span>
                      {formatBytes(document.file_size)} · {formatDate(document.created_at)}
                    </span>
                  </div>
                  <span className={`documents__status documents__status--${document.processing_status}`}>
                    {document.processing_status}
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
                  <dd>{formatBytes(selectedDocument.file_size)}</dd>
                </div>
                <div>
                  <dt>Uploaded</dt>
                  <dd>{formatDate(selectedDocument.created_at)}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{selectedDocument.processing_status}</dd>
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
