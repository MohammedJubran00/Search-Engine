// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

const longName = 'AWS_Academy_Graduate___Cloud_Foundations___Training_Badge_20260522-31-ghrrkk.pdf'
const documents = [
  { id:'one', original_filename:longName, content_type:'application/pdf', file_size:976000, processing_status:'completed', indexing_status:'completed', created_at:'2026-11-01T00:00:00Z' },
  { id:'two', original_filename:'First examF21_SWER385.pdf', content_type:'application/pdf', file_size:239000, processing_status:'completed', indexing_status:'queued', created_at:'2026-11-01T00:00:00Z' },
  { id:'three', original_filename:'Failed document.docx', content_type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document', file_size:35500, processing_status:'completed', indexing_status:'failed', created_at:'2026-11-01T00:00:00Z' },
]

vi.mock('../api/documents', () => ({
  deleteDocument: vi.fn(), indexDocument: vi.fn(), uploadDocument: vi.fn(),
  fetchDocumentPage: vi.fn(async () => ({ items:documents, total:3, offset:0, limit:24 })),
  fetchIndexingJob: vi.fn(async (id) => id === 'two'
    ? { status:'queued', stage:'queued', completed_chunks:0, total_chunks:null }
    : { status:'failed', stage:'failed', completed_chunks:0, total_chunks:null }),
  formatDocumentBytes: (value) => `${value} B`,
}))
vi.mock('../api/documentFiles', () => ({
  DOCUMENT_FILE_ACCEPT:'.pdf,.docx,.txt', validateDocumentFile:() => null,
}))

import DocumentLibrary from './DocumentLibrary'

afterEach(cleanup)

it('keeps long filenames, states, details, and delete actions inside every card', async () => {
  const user = userEvent.setup()
  render(<DocumentLibrary onDocumentsChanged={vi.fn()} />)

  await screen.findByText(longName)
  expect(screen.getAllByRole('button', { name:'Delete document' })).toHaveLength(3)
  expect(screen.getByText('Indexing will start automatically…')).not.toBeNull()
  expect(screen.getByText('Indexed & ready')).not.toBeNull()
  expect(screen.getByText('Indexing failed')).not.toBeNull()

  await user.click(screen.getAllByRole('button', { name:'View details' })[0])
  expect(screen.getByRole('dialog', { name:'Document details' })).not.toBeNull()
  expect(screen.getByText(longName, { selector:'dd' })).not.toBeNull()
  await user.click(screen.getByRole('button', { name:'Close document details' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
})
