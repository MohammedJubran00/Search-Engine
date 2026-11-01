// @vitest-environment jsdom

import { render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

vi.mock('../api/documents', () => ({
  formatDocumentBytes: (value) => `${value} bytes`,
}))

import MessageBubble from './MessageBubble'

it('renders mixed Arabic content RTL while preserving Markdown math', () => {
  const { container } = render(<MessageBubble message={{
    role: 'assistant',
    content: 'شرح عربي للمعادلة $x^2 + y^2$',
    presentation: { type: 'standard' },
  }} />)

  expect(container.querySelector('.message__body')?.getAttribute('dir')).toBe('rtl')
  expect(container.querySelector('.katex')).not.toBeNull()
})

it('preserves the complete answer when final metadata includes a structured presentation', () => {
  const content = [
    'This introduction must remain visible after streaming finishes.',
    '',
    '1. First recommendation',
    '2. Second recommendation',
    '',
    'This conclusion is also part of the answer.',
  ].join('\n')
  const { getByText, queryByRole } = render(<MessageBubble message={{
    role: 'assistant',
    content,
    presentation: {
      type: 'steps',
      headers: [],
      rows: [],
      items: [
        { label: '1', text: 'First recommendation' },
        { label: '2', text: 'Second recommendation' },
      ],
    },
  }} />)

  expect(getByText('This introduction must remain visible after streaming finishes.')).not.toBeNull()
  expect(getByText('This conclusion is also part of the answer.')).not.toBeNull()
  expect(queryByRole('list', { name: 'Steps' })).toBeNull()
})

it('uses structured presentation as a fallback when no answer text exists', () => {
  const { getByRole } = render(<MessageBubble message={{
    role: 'assistant',
    content: '',
    presentation: {
      type: 'steps',
      headers: [],
      rows: [],
      items: [{ label: '1', text: 'Fallback step' }],
    },
  }} />)

  expect(getByRole('list', { name: 'Steps' })).not.toBeNull()
})
