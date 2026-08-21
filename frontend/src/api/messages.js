import { getUserIdFromAccessToken } from './auth'
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

function messagesStorageKey(userId) {
  return `${MESSAGES_STORAGE_KEY}:${userId}`
}

export function loadMessages() {
  const userId = getUserIdFromAccessToken()
  const sessionId = getSessionId()
  if (!userId || !sessionId) return []

  try {
    const raw = localStorage.getItem(messagesStorageKey(userId))
    if (!raw) return []

    const parsed = JSON.parse(raw)
    if (
      !parsed ||
      parsed.user_id !== userId ||
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
  const userId = getUserIdFromAccessToken()
  const sessionId = getSessionId()
  if (!userId || !sessionId) return

  try {
    localStorage.setItem(
      messagesStorageKey(userId),
      JSON.stringify({
        user_id: userId,
        session_id: sessionId,
        messages,
      }),
    )
  } catch {
    // Ignore quota / private-mode failures and keep the in-memory chat
  }
}
