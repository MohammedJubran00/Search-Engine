/*
 * Why it exists: login.html already stores JWTs in localStorage under these
 * keys. Chat must send the same access token so identity is JWT.sub, not
 * session_id.
 *
 * Responsibility: read/clear the access token and send unauthenticated users
 * to Login.
 */

export const ACCESS_TOKEN_KEY = 'ai-search-engine-access-token'
export const REFRESH_TOKEN_KEY = 'ai-search-engine-refresh-token'
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

export function isAuthenticated() {
  return Boolean(getAccessToken())
}

export function authHeaders() {
  const token = getAccessToken()
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

export function clearStoredTokens() {
  try {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  } catch {
    // localStorage can be unavailable
  }
}

export function redirectToLogin() {
  clearStoredTokens()
  window.location.replace(LOGIN_PATH)
}

export function redirectIfUnauthorized(status) {
  if (status !== 401) return false
  redirectToLogin()
  return true
}
