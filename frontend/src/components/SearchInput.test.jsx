// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/documents', () => ({
  DOCUMENT_FILE_ACCEPT: '.pdf,.docx,.txt',
  fetchDocument: vi.fn(),
  formatDocumentBytes: (value) => `${value} bytes`,
  uploadDocument: vi.fn(),
  validateDocumentFile: () => null,
}))

import SearchInput from './SearchInput'

afterEach(cleanup)

const baseProps = {
  disabled: false,
  documents: [],
  attachedDocumentIds: [],
  onAttachDocument: vi.fn(),
  onRemoveDocument: vi.fn(),
  onDocumentUpsert: vi.fn(),
}

describe('SearchInput', () => {
  it('clears immediately and submits once during a rapid double click', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(true)
    render(<SearchInput {...baseProps} onSubmit={onSubmit} />)
    const composer = screen.getByLabelText('Ask a question')
    await user.type(composer, 'Explain the architecture')
    await user.dblClick(screen.getByRole('button', { name: 'Send question' }))

    expect(composer.value).toBe('')
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith('Explain the architecture')
  })

  it('keeps Shift+Enter as a newline', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(true)
    render(<SearchInput {...baseProps} onSubmit={onSubmit} />)
    const composer = screen.getByLabelText('Ask a question')
    await user.type(composer, 'line one')
    await user.keyboard('{Shift>}[Enter]{/Shift}')
    await user.type(composer, 'line two')
    expect(composer.value).toBe('line one\nline two')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('uses Enter to send', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(true)
    render(<SearchInput {...baseProps} onSubmit={onSubmit} />)
    const composer = screen.getByLabelText('Ask a question')
    await user.type(composer, 'send me')
    fireEvent.keyDown(composer, { key: 'Enter', code: 'Enter', shiftKey: false })
    expect(onSubmit).toHaveBeenCalledWith('send me')
  })

  it('keeps uploaded documents out of the composer', () => {
    render(<SearchInput {...baseProps} onSubmit={vi.fn()} documents={[{
      id:'doc-1', original_filename:'Long project document.pdf', file_size:1200,
      indexing_status:'queued',
    }]} attachedDocumentIds={['doc-1']} />)
    expect(screen.queryByText('Long project document.pdf')).toBeNull()
    expect(screen.getByPlaceholderText('Prepare attached documents before sending…')).not.toBeNull()
  })
})
