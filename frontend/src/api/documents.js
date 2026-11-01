import { authorizedFetch } from './auth'
import { readErrorDetail, readJsonResponse } from './errors'
export {
  DOCUMENT_FILE_ACCEPT,
  MAX_DOCUMENT_BYTES,
  SUPPORTED_DOCUMENT_EXTENSIONS,
  formatDocumentBytes,
  validateDocumentFile,
} from './documentFiles'

const DOCUMENTS_URL = '/api/documents'
const NETWORK_ERROR =
  'Could not reach the document service. Make sure the FastAPI server is running.'

function fallbackMessage(status, action) {
  if (status === 400) return 'The document is empty, corrupted, or cannot be parsed.'
  if (status === 401) return 'Your session expired. Please sign in again.'
  if (status === 413) return 'The document is larger than the upload limit.'
  if (status === 415) return 'Only valid PDF, DOCX, and TXT documents are supported.'
  if (status >= 500) return `The server could not ${action} the document. Please try again.`
  return `Could not ${action} the document. Please try again.`
}

async function requireOk(response, action) {
  const payload = response.status === 204 ? null : await readJsonResponse(response)
  if (!response.ok) {
    throw new Error(readErrorDetail(payload, fallbackMessage(response.status, action)))
  }
  return payload
}

async function documentRequest(url, options, action) {
  let response
  try {
    response = await authorizedFetch(url, options)
  } catch {
    throw new Error(NETWORK_ERROR)
  }
  return requireOk(response, action)
}

export async function fetchDocuments() {
  const payload = await documentRequest(DOCUMENTS_URL, undefined, 'load')
  return Array.isArray(payload) ? payload : []
}

export async function fetchDocumentPage({ search = '', status = '', offset = 0 } = {}) {
  const params = new URLSearchParams({ limit: '24', offset: String(offset) })
  if (search.trim()) params.set('search', search.trim())
  if (status) params.set('indexing_status', status)
  const response = await authorizedFetch(`/api/documents/page?${params}`)
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(readErrorDetail(payload, 'Could not load documents.'))
  return payload
}

export async function fetchIndexingJob(documentId) {
  const response = await authorizedFetch(`/api/documents/${documentId}/index-job`)
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(readErrorDetail(payload, 'Could not load indexing status.'))
  return payload
}

export function fetchDocument(documentId) {
  return documentRequest(`${DOCUMENTS_URL}/${documentId}`, undefined, 'load')
}

export function uploadDocument(file) {
  const body = new FormData()
  body.append('file', file)
  return documentRequest(
    `${DOCUMENTS_URL}/upload`,
    { method: 'POST', body },
    'upload',
  )
}

export function indexDocument(documentId) {
  return documentRequest(
    `${DOCUMENTS_URL}/${documentId}/index`,
    { method: 'POST' },
    'prepare',
  )
}

export async function deleteDocument(documentId) {
  await documentRequest(
    `${DOCUMENTS_URL}/${documentId}`,
    { method: 'DELETE' },
    'delete',
  )
}
