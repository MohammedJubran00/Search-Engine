import { authorizedFetch } from './auth'
import { readErrorDetail } from './errors'

const METRICS_URL = '/api/metrics'

export async function fetchUsageMetrics() {
  let response
  try {
    response = await authorizedFetch(METRICS_URL)
  } catch {
    throw new Error('Could not reach the usage service.')
  }

  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  if (!response.ok) {
    throw new Error(readErrorDetail(payload, 'Could not load usage metrics.'))
  }
  return payload
}
