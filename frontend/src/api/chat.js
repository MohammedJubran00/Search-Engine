const CHAT_URL = 'http://127.0.0.1:8000/chat'

function readErrorDetail(payload, fallback) {
  if (!payload || typeof payload !== 'object') return fallback

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

export async function sendChatQuery(query) {
  let response

  try {
    response = await fetch(CHAT_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    })
  } catch {
    throw new Error(
      'Could not reach the search engine. Make sure the FastAPI server is running at http://127.0.0.1:8000.',
    )
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
  if (!answer) {
    throw new Error(
      payload == null
        ? 'The server returned an unexpected response. Please try again.'
        : 'The search engine returned an empty answer. Please try a different question.',
    )
  }

  return answer
}
