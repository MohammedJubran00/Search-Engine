import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteDocument, fetchDocumentPage, formatDocumentBytes,
  indexDocument, uploadDocument,
} from '../api/documents'
import { DOCUMENT_FILE_ACCEPT, validateDocumentFile } from '../api/documentFiles'
import './DocumentLibrary.css'

export default function DocumentLibrary({ onDocumentsChanged }) {
  const [page, setPage] = useState({ items: [], total: 0, offset: 0, limit: 24 })
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const inputRef = useRef(null)

  const load = useCallback(async (offset = 0) => {
    try {
      const result = await fetchDocumentPage({ search, status, offset })
      setError('')
      setPage(result)
      onDocumentsChanged?.(result.items)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not load documents.')
    }
  }, [onDocumentsChanged, search, status])

  // Query changes synchronize this view with the server-side page.
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { void load(0) }, [load])
  useEffect(() => {
    if (!page.items.some((item) => ['queued', 'processing'].includes(item.indexing_status))) return undefined
    const timer = window.setInterval(() => { void load(page.offset) }, 2000)
    return () => window.clearInterval(timer)
  }, [load, page.items, page.offset])

  async function uploadFiles(files) {
    const selected = Array.from(files || [])
    const invalid = selected.map((file) => validateDocumentFile(file)).find(Boolean)
    if (invalid) { setError(invalid); return }
    setBusy(true)
    try {
      for (const file of selected) await uploadDocument(file)
      await load(0)
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Upload failed.')
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function remove(item) {
    if (!window.confirm(`Delete “${item.original_filename}”?`)) return
    await deleteDocument(item.id)
    await load(page.offset)
  }

  async function retry(item) {
    setBusy(true)
    try { await indexDocument(item.id); await load(page.offset) }
    catch (retryError) { setError(retryError instanceof Error ? retryError.message : 'Retry failed.') }
    finally { setBusy(false) }
  }

  return (
    <section className="library">
      <header className="view-heading"><div><span>Knowledge workspace</span><h1>Document Library</h1><p>Upload once. Indexing starts automatically in the durable worker.</p></div><button type="button" onClick={() => inputRef.current?.click()} disabled={busy}>Upload documents</button></header>
      <input ref={inputRef} hidden type="file" multiple accept={DOCUMENT_FILE_ACCEPT} onChange={(event) => uploadFiles(event.target.files)} />
      <div className="library__drop" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void uploadFiles(event.dataTransfer.files) }}>
        Drop PDF, DOCX, or TXT files here, or use Upload documents.
      </div>
      <div className="library__filters"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search documents…" /><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All states</option><option value="queued">Queued</option><option value="processing">Processing</option><option value="completed">Indexed</option><option value="failed">Failed</option></select></div>
      {error ? <p className="view-error" role="alert">{error}</p> : null}
      <div className="library__grid">
        {page.items.map((item) => (
          <article key={item.id} className="document-card">
            <div className="document-card__icon">{item.original_filename.split('.').pop()?.toUpperCase()}</div>
            <div><h2>{item.original_filename}</h2><p>{formatDocumentBytes(item.file_size)} · {new Date(item.created_at).toLocaleDateString()}</p></div>
            <span className={`status status--${item.indexing_status}`}>{item.indexing_status === 'completed' ? 'Indexed' : item.indexing_status}</span>
            <div className="document-card__actions">{item.indexing_status === 'failed' ? <button type="button" onClick={() => retry(item)}>Retry indexing</button> : null}<button type="button" onClick={() => remove(item)}>Delete</button></div>
          </article>
        ))}
      </div>
      {!page.items.length ? <div className="view-empty"><h2>No matching documents</h2><p>Your private library will appear here.</p></div> : null}
      <footer className="library__pagination"><span>{page.total} documents</span><div><button type="button" disabled={page.offset === 0} onClick={() => load(Math.max(0, page.offset - page.limit))}>Previous</button><button type="button" disabled={page.offset + page.limit >= page.total} onClick={() => load(page.offset + page.limit)}>Next</button></div></footer>
    </section>
  )
}
