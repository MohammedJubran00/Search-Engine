import { getUserIdFromAccessToken } from './auth'

const SESSION_STORAGE_KEY = 'ai-search-engine-session-id'

let memorySessionId = ''
let memoryUserId = ''

function createSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
}

function sessionStorageKey(userId) {
  return `${SESSION_STORAGE_KEY}:${userId}`
}

export function getSessionId() {
  const userId = getUserIdFromAccessToken()
  if (!userId) {
    memorySessionId = ''
    memoryUserId = ''
    return ''
  }

  if (memorySessionId && memoryUserId === userId) {
    return memorySessionId
  }

  memoryUserId = userId
  memorySessionId = ''

  try {
    const stored = localStorage.getItem(sessionStorageKey(userId))
    if (stored && stored.trim()) {
      memorySessionId = stored.trim()
      return memorySessionId
    }
  } catch {
    // localStorage can be unavailable in private browsing
  }

  memorySessionId = createSessionId()

  try {
    localStorage.setItem(sessionStorageKey(userId), memorySessionId)
  } catch {
    // Keep the in-memory id for this page even if storage is blocked
  }

  return memorySessionId
}
