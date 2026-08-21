/*
 * Why it exists: login.html already stores JWTs in localStorage under the
 * keys in AUTH_CONFIG. Chat, /me, refresh, and logout must use that same store.
 *
 * Responsibility: read/write tokens, attach Bearer headers, refresh once on
 * 401, and send unauthenticated users to Login.
 */

const AUTH = window.AUTH_CONFIG

export const ACCESS_TOKEN_KEY = AUTH.ACCESS_TOKEN_KEY
export const REFRESH_TOKEN_KEY = AUTH.REFRESH_TOKEN_KEY
export const LOGIN_PATH = AUTH.LOGIN_PATH

const ME_URL = '/api/auth/me'
const REFRESH_URL = '/api/auth/refresh'
const LOGOUT_URL = '/api/auth/logout'

let refreshInFlight = null

function readStorage(key) {
  try {
    const value = localStorage.getItem(key)
    return value && value.trim() ? value.trim() : ''
  } catch {
    return ''
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // localStorage can be unavailable
  }
}

export function getAccessToken() {
  return readStorage(ACCESS_TOKEN_KEY)
}

function getRefreshToken() {
  return readStorage(REFRESH_TOKEN_KEY)
}

export function storeTokens(accessToken, refreshToken) {
  writeStorage(ACCESS_TOKEN_KEY, accessToken)
  writeStorage(REFRESH_TOKEN_KEY, refreshToken)
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

async function refreshSession() {
  if (refreshInFlight) return refreshInFlight

  refreshInFlight = (async () => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) return false

    let response
    try {
      response = await fetch(REFRESH_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
    } catch {
      return false
    }

    if (!response.ok) return false

    let payload = null
    try {
      payload = await response.json()
    } catch {
      return false
    }

    if (!payload?.access_token || !payload?.refresh_token) return false
    storeTokens(payload.access_token, payload.refresh_token)
    return true
  })()

  try {
    return await refreshInFlight
  } finally {
    refreshInFlight = null
  }
}

export async function authorizedFetch(url, options = {}, isRetry = false) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      ...authHeaders(),
    },
  })

  if (response.status !== 401) return response

  if (!isRetry) {
    const refreshed = await refreshSession()
    if (refreshed) {
      return authorizedFetch(url, options, true)
    }
  }

  redirectToLogin()
  return response
}

export async function fetchCurrentUser() {
  const response = await authorizedFetch(ME_URL)
  if (!response.ok) {
    throw new Error('Could not load your account.')
  }
  return response.json()
}

export async function logout() {
  try {
    await fetch(LOGOUT_URL, {
      method: 'POST',
      headers: authHeaders(),
    })
  } catch {
    // Still clear local tokens if the API is unreachable.
  }
  redirectToLogin()
}
