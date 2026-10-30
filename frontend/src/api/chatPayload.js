export function buildChatPayload(query, options = {}) {
  const { conversationId, mode = 'general', documentIds = [] } = options
  const body = { query, mode }
  if (conversationId) body.conversation_id = conversationId
  if (mode === 'documents' && documentIds.length) {
    body.document_ids = [...new Set(documentIds)]
  }
  return body
}

export function readDocumentStreamMetadata(payload, fallbackMode = 'general') {
  if (
    payload?.mode !== 'documents' &&
    typeof payload?.status !== 'string' &&
    !Array.isArray(payload?.citations) &&
    !Array.isArray(payload?.web_citations)
  ) {
    return null
  }
  return {
    mode: payload.mode || fallbackMode,
    status: payload.status || null,
    citations: Array.isArray(payload.citations) ? payload.citations : [],
    webCitations: Array.isArray(payload.web_citations) ? payload.web_citations : [],
  }
}
