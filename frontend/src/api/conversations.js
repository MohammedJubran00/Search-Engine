import { authorizedFetch } from './auth'
import { readErrorDetail } from './errors'

async function request(url, options) {
  const response = await authorizedFetch(url, options)
  if (response.status === 204) return null
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(readErrorDetail(payload, 'Conversation request failed.'))
  return payload
}

export function fetchConversations(search = '', offset = 0) {
  const params = new URLSearchParams({ limit: '50', offset: String(offset) })
  if (search.trim()) params.set('search', search.trim())
  return request(`/api/conversations?${params}`)
}

export function createConversation(mode = 'general') {
  return request('/api/conversations', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'New chat', mode }),
  })
}

export function fetchConversation(id) { return request(`/api/conversations/${id}`) }
export function updateConversation(id, changes) {
  return request(`/api/conversations/${id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  })
}
export function renameConversation(id, title) { return updateConversation(id, { title }) }
export function deleteConversation(id) {
  return request(`/api/conversations/${id}`, { method: 'DELETE' })
}
export function updateConversationDocuments(id, documentIds) {
  return request(`/api/conversations/${id}/documents`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_ids: documentIds }),
  })
}
