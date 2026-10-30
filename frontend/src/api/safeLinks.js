export function isSafeHref(href, base = 'http://localhost') {
  if (!href || typeof href !== 'string') return false
  try {
    const url = new URL(href, base)
    return url.protocol === 'http:' || url.protocol === 'https:' || url.protocol === 'mailto:'
  } catch {
    return false
  }
}
