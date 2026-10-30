const configuredMaxBytes = Number.parseInt(
  import.meta.env?.VITE_RAG_MAX_UPLOAD_BYTES || '10485760',
  10,
)

export const MAX_DOCUMENT_BYTES =
  Number.isFinite(configuredMaxBytes) && configuredMaxBytes > 0
    ? configuredMaxBytes
    : 10 * 1024 * 1024

export const SUPPORTED_DOCUMENT_EXTENSIONS = new Set(['pdf', 'docx', 'txt'])
export const DOCUMENT_FILE_ACCEPT =
  '.pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain'

export function formatDocumentBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return 'Unknown size'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

export function validateDocumentFile(file) {
  if (!file) return 'Choose a document first.'
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (!extension || !SUPPORTED_DOCUMENT_EXTENSIONS.has(extension)) {
    return 'Choose a PDF, DOCX, or TXT document.'
  }
  if (file.size === 0) return 'The selected document is empty.'
  if (file.size > MAX_DOCUMENT_BYTES) {
    return `The document must be ${formatDocumentBytes(MAX_DOCUMENT_BYTES)} or smaller.`
  }
  return ''
}
