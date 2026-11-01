import { authorizedFetch } from './auth'
import { readErrorDetail } from './errors'

async function request(options) {
  const response = await authorizedFetch('/api/preferences', options)
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(readErrorDetail(payload, 'Could not load settings.'))
  return payload
}

export function fetchPreferences() { return request() }
export function savePreferences(preferences) {
  return request({
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(preferences),
  })
}
