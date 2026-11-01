import { authorizedFetch } from './auth'
import { readErrorDetail } from './errors'
import { buildChatPayload, readDocumentStreamMetadata } from './chatPayload'

const CHAT_STREAM_URL = '/chat/stream'
const LATEST_CONVERSATION_URL = '/api/conversations/latest'
const UNREACHABLE =
  'Could not reach the search engine. Make sure the FastAPI server is running at http://127.0.0.1:8000.'

function jsonHeaders() {
  return {
    'Content-Type': 'application/json',
  }
}

export async function fetchLatestConversation() {
  let response
  try {
    response = await authorizedFetch(LATEST_CONVERSATION_URL)
  } catch {
    throw new Error(UNREACHABLE)
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
  const {
    conversationId,
    onConversationId,
    onMetadata,
    mode,
    documentIds,
    researchMode,
    responseDepth,
    responseLanguage,
    signal,
  } = options
  let response

  try {
    response = await authorizedFetch(CHAT_STREAM_URL, {
      method: 'POST',
      headers: {
        ...jsonHeaders(),
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(
        buildChatPayload(query, { conversationId, mode, documentIds, researchMode, responseDepth, responseLanguage }),
      ),
      signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new Error(UNREACHABLE)
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
  let completed = false
  let resolvedConversationId = conversationId || null

  try {
    while (!completed) {
      const { value, done } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() ?? ''

      for (const block of blocks) {
        if (completed) break
        let payload
        try {
          payload = parseSseBlock(block)
        } catch {
          throw new Error('The server returned invalid stream data. Please try again.')
        }

        if (!payload) continue
        if (payload.done === true) completed = true

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

        const metadata = readDocumentStreamMetadata(payload, mode || 'general')
        if (metadata && !payload.done) onMetadata?.(metadata)
      }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }

  if (!completed) {
    throw new Error('The answer stream was interrupted before completion. Please try again.')
  }

  if (!answer.trim()) {
    throw new Error(
      'The search engine returned an empty answer. Please try a different question.',
    )
  }

  return { answer, conversationId: resolvedConversationId }
}
