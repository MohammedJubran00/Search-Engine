// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import Sidebar from './Sidebar'

it('navigates, searches, starts, selects, renames, and deletes conversations', async () => {
  const user = userEvent.setup()
  const handlers = {
    onToggle: vi.fn(), onView: vi.fn(), onSelectConversation: vi.fn(),
    onNewChat: vi.fn(), onRename: vi.fn(), onDelete: vi.fn(), onSearch: vi.fn(),
  }
  const conversation = {
    id: 'c1', title: 'Architecture review', updated_at: new Date().toISOString(),
  }
  render(
    <Sidebar {...handlers} collapsed={false} view="chat" activeId="c1"
      conversations={[conversation]} search="" />,
  )

  await user.click(screen.getByRole('button', { name: /New research chat/i }))
  await user.click(screen.getByRole('button', { name: /Document Library/i }))
  fireEvent.change(screen.getByPlaceholderText('Search conversations…'), { target: { value: 'vector' } })
  await user.click(screen.getByRole('button', { name: 'Architecture review' }))
  await user.click(screen.getByRole('button', { name: 'Rename Architecture review' }))
  await user.click(screen.getByRole('button', { name: 'Delete Architecture review' }))

  expect(handlers.onNewChat).toHaveBeenCalledTimes(1)
  expect(handlers.onView).toHaveBeenCalledWith('documents')
  expect(handlers.onSearch).toHaveBeenLastCalledWith('vector')
  expect(handlers.onSelectConversation).toHaveBeenCalledWith('c1')
  expect(handlers.onRename).toHaveBeenCalledWith(conversation)
  expect(handlers.onDelete).toHaveBeenCalledWith(conversation)
})
