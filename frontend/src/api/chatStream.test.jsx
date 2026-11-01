import { afterEach, expect, it, vi } from 'vitest'
import { ReadableStream } from 'node:stream/web'
import { TextEncoder } from 'node:util'

vi.mock('./auth', () => ({ authorizedFetch: vi.fn() }))
import { authorizedFetch } from './auth'
import { streamChatQuery } from './chat'

afterEach(() => vi.resetAllMocks())

function responseFor(events) {
  const bytes = new TextEncoder().encode(events.map((event) => `data: ${JSON.stringify(event)}\r\n\r\n`).join(''))
  return new Response(new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(new Uint8Array([byte]))
    controller.close()
  } }))
}

it('accumulates fragmented UTF-8 content without duplicating final text or clearing citations', async () => {
  authorizedFetch.mockResolvedValue(responseFor([
    { conversation_id: 'test' }, { delta: 'مرحبا ' }, { delta: '**world** [S1].' },
    { mode: 'documents', status: 'answered', citations: [{ label: 'S1' }] },
    { done: true, mode: 'documents', status: 'answered' },
  ]))
  const onText = vi.fn(), onMetadata = vi.fn()
  const result = await streamChatQuery('question', onText, { mode: 'documents', onMetadata })
  expect(onText.mock.calls.map(([value]) => value)).toEqual(['مرحبا ', 'مرحبا **world** [S1].'])
  expect(result.answer).toBe('مرحبا **world** [S1].')
  expect(onMetadata).toHaveBeenCalledTimes(1)
  expect(onMetadata.mock.calls[0][0].citations).toEqual([{ label: 'S1' }])
})

it('rejects truncated streams instead of treating partial content as a completed answer', async () => {
  authorizedFetch.mockResolvedValue(responseFor([{ delta: 'partial' }]))
  await expect(streamChatQuery('question', vi.fn())).rejects.toThrow('interrupted')
})

it('does not accept a provisional answer when final validation fails', async () => {
  authorizedFetch.mockResolvedValue(responseFor([{ delta: 'partial [S99]' }, { error: 'Invalid citation', discard_partial: true }]))
  await expect(streamChatQuery('question', vi.fn())).rejects.toThrow('Invalid citation')
})

it('preserves AbortError when stopped before response headers', async () => {
  authorizedFetch.mockRejectedValue(new DOMException('Stopped', 'AbortError'))
  await expect(streamChatQuery('question', vi.fn())).rejects.toHaveProperty('name', 'AbortError')
})
