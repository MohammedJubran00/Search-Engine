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
