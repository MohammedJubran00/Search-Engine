import { authHeaders, redirectIfUnauthorized } from './auth'

const CHAT_URL = '/chat'
const CHAT_STREAM_URL = '/chat/stream'
const LATEST_CONVERSATION_URL = '/api/conversations/latest'

function readErrorDetail(payload, fallback) {
  if (!payload || typeof payload !== 'object') return fallback

  if (typeof payload.error === 'string' && payload.error.trim()) {
    return payload.error.trim()
  }

  const detail = payload.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => item.msg || item.message || JSON.stringify(item))
      .join(' ')
  }
  if (typeof payload.message === 'string' && payload.message.trim()) {
    return payload.message
  }

  return fallback
}

function extractText(value) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)

  if (Array.isArray(value)) {
    return value
      .map((item) => extractText(item))
      .filter(Boolean)
      .join('\n\n')
  }

  if (typeof value !== 'object') return ''

  if (value.type === 'thinking' || value.type === 'reasoning') {
    return ''
  }

  if (typeof value.text === 'string') return value.text
  if (typeof value.answer === 'string') return value.answer
  if (typeof value.content === 'string') return value.content
  if (value.content != null) return extractText(value.content)
  if (value.parts != null) return extractText(value.parts)

  return ''
}

function extractAnswer(payload) {
  if (payload == null) return ''
  if (typeof payload === 'string') return payload.trim()

  const raw =
    payload.answer ?? payload.response ?? payload.output ?? payload.content ?? payload

  return extractText(raw).trim()
}

function jsonHeaders() {
  return {
    'Content-Type': 'application/json',
    ...authHeaders(),
  }
}

function chatBody(query, conversationId) {
  const body = { query }
  if (conversationId) {
    body.conversation_id = conversationId
  }
  return JSON.stringify(body)
}

export async function fetchLatestConversation() {
  let response
  try {
    response = await fetch(LATEST_CONVERSATION_URL, {
      headers: authHeaders(),
    })
  } catch {
    throw new Error(
      'Could not reach the search engine. Make sure the FastAPI server is running at http://127.0.0.1:8000.',
    )
  }

  if (redirectIfUnauthorized(response.status)) {
    throw new Error('Not authenticated.')
  }

  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    throw new Error(
      readErrorDetail(payload, 'Could not load your conversation. Please try again.'),
    )
  }

  return {
    conversationId: payload?.conversation_id || null,
    messages: Array.isArray(payload?.messages) ? payload.messages : [],
  }
}

export async function sendChatQuery(query, conversationId) {
  let response

  try {
    response = await fetch(CHAT_URL, {
      method: 'POST',
      headers: jsonHeaders(),
      body: chatBody(query, conversationId),
    })
  } catch {
    throw new Error(
      'Could not reach the search engine. Make sure the FastAPI server is running at http://127.0.0.1:8000.',
    )
  }

  if (redirectIfUnauthorized(response.status)) {
    throw new Error('Not authenticated.')
  }

  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    throw new Error(
      readErrorDetail(
        payload,
        `The search engine could not complete this request (${response.status}). Please try again.`,
      ),
    )
  }

  const answer = extractAnswer(payload)
  if (
    payload &&
    typeof payload.error === 'string' &&
    payload.error.trim() &&
    !answer
  ) {
    throw new Error(payload.error.trim())
  }

  if (!answer) {
    throw new Error(
      payload == null
        ? 'The server returned an unexpected response. Please try again.'
        : 'The search engine returned an empty answer. Please try a different question.',
    )
  }

  return {
    answer,
    conversationId: payload?.conversation_id || conversationId || null,
  }
}

function parseSseBlock(block) {
  const data = block
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')

  if (!data) return null
  return JSON.parse(data)
}

export async function streamChatQuery(query, onDelta, options = {}) {
  const { conversationId, onConversationId } = options
  let response

  try {
    response = await fetch(CHAT_STREAM_URL, {
      method: 'POST',
      headers: {
        ...jsonHeaders(),
        Accept: 'text/event-stream',
      },
      body: chatBody(query, conversationId),
    })
  } catch {
    throw new Error(
      'Could not reach the search engine. Make sure the FastAPI server is running at http://127.0.0.1:8000.',
    )
  }

  if (redirectIfUnauthorized(response.status)) {
    throw new Error('Not authenticated.')
  }

  if (!response.ok) {
    let payload = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }

    throw new Error(
      readErrorDetail(
        payload,
        `The search engine could not complete this request (${response.status}). Please try again.`,
      ),
    )
  }

  if (!response.body) {
    throw new Error('The server returned an unexpected response. Please try again.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let answer = ''
  let resolvedConversationId = conversationId || null

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''

    for (const block of blocks) {
      let payload
      try {
        payload = parseSseBlock(block)
      } catch {
        continue
      }

      if (!payload) continue

      if (typeof payload.conversation_id === 'string' && payload.conversation_id) {
        resolvedConversationId = payload.conversation_id
        onConversationId?.(payload.conversation_id)
      }

      if (typeof payload.error === 'string' && payload.error.trim()) {
        throw new Error(payload.error.trim())
      }

      if (typeof payload.delta === 'string' && payload.delta) {
        answer += payload.delta
        onDelta(answer)
      }
    }
  }

  if (!answer.trim()) {
    throw new Error(
      'The search engine returned an empty answer. Please try a different question.',
    )
  }

  return { answer, conversationId: resolvedConversationId }
}
