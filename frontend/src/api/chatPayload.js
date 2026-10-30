export function buildChatPayload(query, options = {}) {
  const {
    conversationId,
    mode = 'general',
    documentIds = [],
    researchMode = 'standard',
  } = options
  const body = { query, mode, research_mode: mode === 'general' ? researchMode : 'standard' }
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
    researchPlan: Array.isArray(payload.research_plan) ? payload.research_plan : [],
    researchSummary:
      payload.research_summary && typeof payload.research_summary === 'object'
        ? payload.research_summary
        : null,
    evidenceConflicts: Array.isArray(payload.evidence_conflicts)
      ? payload.evidence_conflicts
      : [],
    presentation:
      payload.presentation && typeof payload.presentation === 'object'
        ? payload.presentation
        : { type: 'standard', headers: [], rows: [], items: [] },
  }
}
