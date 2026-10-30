import assert from 'node:assert/strict'
import test from 'node:test'

import { buildChatPayload, readDocumentStreamMetadata } from './chatPayload.js'

test('general chat never carries document context', () => {
  assert.deepEqual(
    buildChatPayload('hello', {
      mode: 'general',
      documentIds: ['private-document'],
    }),
    { query: 'hello', mode: 'general', research_mode: 'standard' },
  )
})

test('document chat sends a deduplicated explicit selection', () => {
  assert.deepEqual(
    buildChatPayload('summarize', {
      conversationId: 'conversation',
      mode: 'documents',
      research_mode: 'standard',
      documentIds: ['one', 'one', 'two'],
    }),
    {
      query: 'summarize',
      mode: 'documents',
      research_mode: 'standard',
      conversation_id: 'conversation',
      document_ids: ['one', 'two'],
    },
  )
})

test('document SSE metadata preserves answerability and citations', () => {
  const citations = [{ label: 'S1', filename: 'project.pdf', page_number: 2 }]
  assert.deepEqual(
    readDocumentStreamMetadata({
      mode: 'documents',
      status: 'insufficient_evidence',
      citations,
    }),
    {
      mode: 'documents',
      status: 'insufficient_evidence',
      citations,
      webCitations: [],
      researchPlan: [],
      researchSummary: null,
      evidenceConflicts: [],
    },
  )
  assert.equal(readDocumentStreamMetadata({ delta: 'legacy general token' }), null)
})

test('general chat stream metadata preserves verified web sources', () => {
  const webCitations = [{ title: 'Primary source', url: 'https://example.com/source' }]
  assert.deepEqual(
    readDocumentStreamMetadata({ mode: 'general', web_citations: webCitations }),
    {
      mode: 'general',
      status: null,
      citations: [],
      webCitations,
      researchPlan: [],
      researchSummary: null,
      evidenceConflicts: [],
    },
  )
})

test('deep research is explicit and never leaks into document mode', () => {
  assert.equal(
    buildChatPayload('compare', { mode: 'general', researchMode: 'deep' }).research_mode,
    'deep',
  )
  assert.equal(
    buildChatPayload('compare', { mode: 'documents', researchMode: 'deep' }).research_mode,
    'standard',
  )
})
