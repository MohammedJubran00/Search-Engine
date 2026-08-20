const SESSION_STORAGE_KEY = 'ai-search-engine-session-id'

let memorySessionId = ''

function createSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
}

export function getSessionId() {
  if (memorySessionId) {
    return memorySessionId
  }

  try {
    const stored = localStorage.getItem(SESSION_STORAGE_KEY)
    if (stored && stored.trim()) {
      memorySessionId = stored.trim()
      return memorySessionId
    }
  } catch {
    // localStorage can be unavailable in private browsing
  }

  memorySessionId = createSessionId()

  try {
    localStorage.setItem(SESSION_STORAGE_KEY, memorySessionId)
  } catch {
    // Keep the in-memory id for this page even if storage is blocked
  }

  return memorySessionId
}
