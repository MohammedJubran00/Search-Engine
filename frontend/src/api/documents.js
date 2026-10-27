import { authorizedFetch } from './auth'
import { readErrorDetail, readJsonResponse } from './errors'

const DOCUMENTS_URL = '/api/documents'
const configuredMaxBytes = Number.parseInt(
  import.meta.env.VITE_RAG_MAX_UPLOAD_BYTES || '10485760',
  10,
)

export const MAX_DOCUMENT_BYTES =
  Number.isFinite(configuredMaxBytes) && configuredMaxBytes > 0
    ? configuredMaxBytes
    : 10 * 1024 * 1024

export const SUPPORTED_DOCUMENT_EXTENSIONS = new Set(['pdf', 'docx', 'txt'])

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

export async function deleteDocument(documentId) {
  await documentRequest(
    `${DOCUMENTS_URL}/${documentId}`,
    { method: 'DELETE' },
    'delete',
  )
}
