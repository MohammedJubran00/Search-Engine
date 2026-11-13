import { useEffect, useMemo, useRef, useState } from 'react'
import {
  DOCUMENT_FILE_ACCEPT,
  fetchDocument,
  formatDocumentBytes,
  uploadDocument,
  validateDocumentFile,
} from '../api/documents'
import './SearchInput.css'

function fileKind(name) {
  return name.split('.').pop()?.toUpperCase() || 'FILE'
}

export default function SearchInput({
  onSubmit,
  disabled,
  documents,
  attachedDocumentIds,
  onAttachDocument,
  onDocumentUpsert,
}) {
  const [value, setValue] = useState('')
  const [pendingFiles, setPendingFiles] = useState([])
  const [menuOpen, setMenuOpen] = useState(false)
  const [composerStatus, setComposerStatus] = useState('')
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)
  const attachedDocuments = useMemo(
    () => documents.filter((item) => attachedDocumentIds.includes(item.id)),
    [attachedDocumentIds, documents],
  )
  const blocked = pendingFiles.length > 0 || attachedDocuments.some(
    (item) => item.indexing_status !== 'completed',
  )
  const canSend = value.trim().length > 0 && !disabled && !blocked

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }, [value])

  useEffect(() => {
    if (!disabled) textareaRef.current?.focus()
  }, [disabled])

  useEffect(() => {
    const pending = attachedDocuments.filter((item) => ['queued', 'processing'].includes(item.indexing_status))
    if (!pending.length) return undefined
    const timer = window.setInterval(async () => {
      for (const item of pending) {
        try { onDocumentUpsert(await fetchDocument(item.id)) } catch { /* next poll retries */ }
      }
    }, 2000)
    return () => window.clearInterval(timer)
  }, [attachedDocuments, onDocumentUpsert])

  function handleFiles(files) {
    const next = Array.from(files || []).map((file) => ({
      key: `${file.name}-${file.size}-${file.lastModified}`,
      file,
      state: 'selected',
      error: validateDocumentFile(file),
    }))
    setPendingFiles((current) => [
      ...current,
      ...next.filter((item) => !current.some((existing) => existing.key === item.key)),
    ])
    setMenuOpen(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function handleUpload(item) {
    if (item.error || item.state === 'uploading') return
    setPendingFiles((current) => current.map((entry) =>
      entry.key === item.key ? { ...entry, state: 'uploading' } : entry,
    ))
    try {
      const uploaded = await uploadDocument(item.file)
      onDocumentUpsert(uploaded)
      onAttachDocument(uploaded.id)
      setPendingFiles((current) => current.filter((entry) => entry.key !== item.key))
      setComposerStatus(uploaded.indexing_status === 'completed'
        ? 'Document ready to use.'
        : 'Document uploaded. Preparing it for use…')
    } catch (error) {
      setPendingFiles((current) => current.map((entry) =>
        entry.key === item.key
          ? { ...entry, state: 'failed', error: error instanceof Error ? error.message : 'Upload failed.' }
          : entry,
      ))
    }
  }

  async function handleSubmit() {
    if (!canSend) return
    const submitted = value
    setValue('')
    setComposerStatus('')
    await onSubmit(submitted)
  }

  return (
    <form className="search-input" onSubmit={(event) => { event.preventDefault(); void handleSubmit() }}>
      {pendingFiles.length ? (
        <div className="search-input__attachments" aria-label="Message attachments">
          {pendingFiles.map((item) => (
            <article key={item.key} className="attachment-card">
              <span className="attachment-card__icon">{fileKind(item.file.name)}</span>
              <span className="attachment-card__text">
                <strong>{item.file.name}</strong>
                <small>{formatDocumentBytes(item.file.size)} · {item.error || (item.state === 'uploading' ? 'Uploading / processing…' : 'Selected locally')}</small>
              </span>
              {item.state !== 'uploading' ? <button type="button" disabled={Boolean(item.error)} onClick={() => handleUpload(item)}>Upload</button> : null}
              <button type="button" aria-label={`Remove ${item.file.name}`} disabled={item.state === 'uploading'} onClick={() => setPendingFiles((current) => current.filter((entry) => entry.key !== item.key))}>×</button>
            </article>
          ))}
        </div>
      ) : null}
      {composerStatus ? <p className="search-input__status" role="status">{composerStatus}</p> : null}
      {attachedDocuments.some((item) => item.indexing_status === 'failed') ? <p className="search-input__status" role="alert">Document indexing failed. Open Document Library to see the reason and retry later, or remove the attachment.</p> : null}
      <label className="visually-hidden" htmlFor="search-query">Ask a question</label>
      <div className="search-input__bar">
        <div className="search-input__attach-wrap">
          <button type="button" className="search-input__attach" aria-label="Attach a document" aria-expanded={menuOpen} onClick={() => setMenuOpen((current) => !current)}>+</button>
          {menuOpen ? (
            <div className="search-input__attach-menu">
              <button type="button" onClick={() => fileInputRef.current?.click()}>Upload PDF, DOCX, or TXT</button>
            </div>
          ) : null}
          <input ref={fileInputRef} className="visually-hidden" type="file" multiple accept={DOCUMENT_FILE_ACCEPT} onChange={(event) => handleFiles(event.target.files)} />
        </div>
        <textarea
          id="search-query"
          ref={textareaRef}
          className="search-input__field"
          rows={1}
          value={value}
          placeholder={blocked ? 'Prepare attached documents before sending…' : 'Ask anything…'}
          autoComplete="off"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void handleSubmit() } }}
          enterKeyHint="send"
        />
        <button type="submit" className="search-input__send" disabled={!canSend} aria-label={disabled ? 'Waiting for answer' : 'Send question'}>
          {disabled ? <span className="search-input__spinner" aria-hidden="true" /> : 'Send'}
        </button>
      </div>
      <p className="search-input__hint">Uploads index automatically. Only indexed documents can be used for answers.</p>
    </form>
  )
}
