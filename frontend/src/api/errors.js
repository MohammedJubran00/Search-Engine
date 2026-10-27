export function readErrorDetail(payload, fallback) {
  if (!payload || typeof payload !== 'object') return fallback

  if (typeof payload.error === 'string' && payload.error.trim()) {
    return payload.error.trim()
  }

  const detail = payload.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => item.msg || item.message || JSON.stringify(item))
      .join(' ')
  }
  if (typeof payload.message === 'string' && payload.message.trim()) {
    return payload.message.trim()
  }

  return fallback
}

export async function readJsonResponse(response) {
  try {
    return await response.json()
  } catch {
    return null
  }
}
