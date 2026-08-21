/*
 * Why it exists: login.html already stores JWTs in localStorage under these
 * keys. The React chat app needs the same storage so it does not invent a
 * second auth mechanism.
 *
 * Responsibility: read the access token and send unauthenticated users to Login.
 */

export const ACCESS_TOKEN_KEY = 'ai-search-engine-access-token'
export const LOGIN_PATH = '/login.html'
export const CHAT_PATH = '/app.html'

export function getAccessToken() {
  try {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY)
    return token && token.trim() ? token.trim() : ''
  } catch {
    return ''
  }
}

export function getUserIdFromAccessToken() {
  const token = getAccessToken()
  const parts = token.split('.')
  if (parts.length < 2) return ''

  try {
    const normalized = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4)
    const payload = JSON.parse(atob(padded))
    return typeof payload.sub === 'string' && payload.sub.trim() ? payload.sub.trim() : ''
  } catch {
    return ''
  }
}

export function isAuthenticated() {
  return Boolean(getAccessToken())
}

export function redirectToLogin() {
  window.location.replace(LOGIN_PATH)
}
