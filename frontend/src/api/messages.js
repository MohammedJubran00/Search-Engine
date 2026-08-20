import { getSessionId } from './session'

const MESSAGES_STORAGE_KEY = 'ai-search-engine-messages'

function isValidMessage(message) {
  return (
    message &&
    typeof message === 'object' &&
    typeof message.id === 'string' &&
    (message.role === 'user' || message.role === 'assistant') &&
    typeof message.content === 'string'
  )
}

export function loadMessages() {
  const sessionId = getSessionId()

  try {
    const raw = localStorage.getItem(MESSAGES_STORAGE_KEY)
    if (!raw) return []

    const parsed = JSON.parse(raw)
    if (
      !parsed ||
      parsed.session_id !== sessionId ||
      !Array.isArray(parsed.messages)
    ) {
      return []
    }

    return parsed.messages.filter(isValidMessage)
  } catch {
    return []
  }
}

export function saveMessages(messages) {
  const sessionId = getSessionId()

  try {
    localStorage.setItem(
      MESSAGES_STORAGE_KEY,
      JSON.stringify({
        session_id: sessionId,
        messages,
      }),
    )
  } catch {
    // Ignore quota / private-mode failures and keep the in-memory chat
  }
}
