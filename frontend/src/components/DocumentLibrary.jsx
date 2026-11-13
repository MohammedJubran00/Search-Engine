import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteDocument, fetchDocumentPage, fetchIndexingJob, formatDocumentBytes,
  indexDocument, uploadDocument,
} from '../api/documents'
import { DOCUMENT_FILE_ACCEPT, validateDocumentFile } from '../api/documentFiles'
import './DocumentLibrary.css'
import { confirmAction } from './AppDialog'

export default function DocumentLibrary({ onDocumentsChanged }) {
  const [page, setPage] = useState({ items: [], total: 0, offset: 0, limit: 24 })
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [jobs, setJobs] = useState({})
  const [detail, setDetail] = useState(null)
  const inputRef = useRef(null)

  const load = useCallback(async (offset = 0) => {
    try {
      const result = await fetchDocumentPage({ search, status, offset })
      setError('')
      setPage(result)
      onDocumentsChanged?.(result.items)
      const tracked = result.items.filter((item) =>
        ['queued', 'processing', 'failed'].includes(item.indexing_status),
      )
      const jobEntries = await Promise.all(tracked.map(async (item) => {
        try { return [item.id, await fetchIndexingJob(item.id)] }
        catch { return [item.id, null] }
      }))
      setJobs(Object.fromEntries(jobEntries))
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
    if (!await confirmAction(`Delete “${item.original_filename}”?`)) return
    await deleteDocument(item.id)
    await load(page.offset)
  }

  async function retry(item) {
    setBusy(true)
    try { await indexDocument(item.id); await load(page.offset) }
    catch (retryError) { setError(retryError instanceof Error ? retryError.message : 'Retry failed.') }
    finally { setBusy(false) }
  }

  function statusLabel(value) {
    return {
      completed: 'Indexed & ready', processing: 'Indexing now', queued: 'Queued',
      failed: 'Indexing failed', not_indexed: 'Not indexed',
    }[value] || value
  }

  function stageLabel(job, item) {
    if (item.indexing_status === 'failed') return job?.error_message || 'Indexing failed. Retry later.'
    if (item.indexing_status === 'queued') return 'Indexing will start automatically…'
    if (!job) return item.indexing_status === 'processing' ? 'Preparing document…' : ''
    const stage = String(job.stage || '').replaceAll('_', ' ')
    if (job.total_chunks && job.status === 'processing') {
      return `${stage} · ${job.completed_chunks}/${job.total_chunks} chunks`
    }
    return stage
  }

  const detailItem = detail
    ? page.items.find((item) => item.id === detail.id) || detail
    : null

  return (
    <section className="library">
      <header className="view-heading"><div><span>Knowledge workspace</span><h1>Document Library</h1><p>Upload a document and indexing starts automatically.</p></div><button type="button" onClick={() => inputRef.current?.click()} disabled={busy}>Upload documents</button></header>
      <input ref={inputRef} hidden type="file" multiple accept={DOCUMENT_FILE_ACCEPT} onChange={(event) => uploadFiles(event.target.files)} />
      <div className="library__drop" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void uploadFiles(event.dataTransfer.files) }}>
        Drop PDF, DOCX, or TXT files here, or use Upload documents.
      </div>
      <div className="library__filters"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search documents…" /><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All states</option><option value="queued">Queued</option><option value="processing">Processing</option><option value="completed">Indexed</option><option value="failed">Failed</option></select></div>
      {error ? <p className="view-error" role="alert">{error}</p> : null}
      <div className="library__grid">
        {page.items.map((item) => (
          <article key={item.id} className="document-card">
            <div className="document-card__top">
              <div className="document-card__icon">{item.original_filename.split('.').pop()?.toUpperCase()}</div>
              <span className={`status status--${item.indexing_status}`}>{statusLabel(item.indexing_status)}</span>
            </div>
            <div className="document-card__details">
              <h2 title={item.original_filename}>{item.original_filename}</h2>
              <p>{formatDocumentBytes(item.file_size)} <span aria-hidden="true">·</span> {new Date(item.created_at).toLocaleDateString()}</p>
              {['queued', 'processing', 'failed'].includes(item.indexing_status) ? (
                <div className="document-card__progress">
                  <span>{stageLabel(jobs[item.id], item)}</span>
                  {jobs[item.id]?.total_chunks && item.indexing_status === 'processing' ? (
                    <progress value={jobs[item.id].completed_chunks} max={jobs[item.id].total_chunks} />
                  ) : null}
                </div>
              ) : <p className="document-card__ready">Ready for Document Chat</p>}
            </div>
            <div className="document-card__actions">
              <button type="button" onClick={() => setDetail(item)}>View details</button>
              {item.indexing_status === 'failed' ? <button type="button" onClick={() => retry(item)} disabled={busy}>Retry indexing</button> : null}
              <button type="button" className="document-card__delete" onClick={() => remove(item)}>Delete document</button>
            </div>
          </article>
        ))}
      </div>
      {!page.items.length ? <div className="view-empty"><h2>No matching documents</h2><p>Your private library will appear here.</p></div> : null}
      <footer className="library__pagination"><span>{page.total} documents</span><div><button type="button" disabled={page.offset === 0} onClick={() => load(Math.max(0, page.offset - page.limit))}>Previous</button><button type="button" disabled={page.offset + page.limit >= page.total} onClick={() => load(page.offset + page.limit)}>Next</button></div></footer>
      {detailItem ? (
        <div className="document-dialog__backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setDetail(null) }}>
          <section className="document-dialog" role="dialog" aria-modal="true" aria-labelledby="document-dialog-title">
            <div className="document-dialog__heading"><div><span>{detailItem.original_filename.split('.').pop()?.toUpperCase()}</span><h2 id="document-dialog-title">Document details</h2></div><button type="button" aria-label="Close document details" onClick={() => setDetail(null)}>×</button></div>
            <dl>
              <div><dt>Filename</dt><dd>{detailItem.original_filename}</dd></div>
              <div><dt>File size</dt><dd>{formatDocumentBytes(detailItem.file_size)}</dd></div>
              <div><dt>Uploaded</dt><dd>{new Date(detailItem.created_at).toLocaleString()}</dd></div>
              <div><dt>Parsing status</dt><dd>{detailItem.processing_status}</dd></div>
              <div><dt>Indexing status</dt><dd>{statusLabel(detailItem.indexing_status)}</dd></div>
              {jobs[detailItem.id] ? <div><dt>Current stage</dt><dd>{stageLabel(jobs[detailItem.id], detailItem)}</dd></div> : null}
            </dl>
            <div className="document-dialog__actions">{detailItem.indexing_status === 'failed' ? <button type="button" onClick={() => retry(detailItem)}>Retry indexing</button> : null}<button type="button" className="document-card__delete" onClick={() => { setDetail(null); void remove(detailItem) }}>Delete document</button></div>
          </section>
        </div>
      ) : null}
    </section>
  )
}
