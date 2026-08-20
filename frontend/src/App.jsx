import { useCallback, useEffect, useRef, useState } from 'react'
import { sendChatQuery } from './api/chat'
import { loadMessages, saveMessages } from './api/messages'
import ChatWindow from './components/ChatWindow'
import Header from './components/Header'
import SearchInput from './components/SearchInput'
import './App.css'

let messageSeq = 0

function nextMessageId() {
  messageSeq += 1
  return `msg-${messageSeq}`
}

function createMessage(partial) {
  return {
    id: nextMessageId(),
    ...partial,
  }
}

function restoreMessageSeq(messages) {
  let maxId = 0
  for (const message of messages) {
    const match = /^msg-(\d+)$/.exec(message.id)
    if (match) {
      maxId = Math.max(maxId, Number(match[1]))
    }
  }
  messageSeq = maxId
}

export default function App() {
  const [messages, setMessages] = useState(() => {
    const restored = loadMessages()
    restoreMessageSeq(restored)
    return restored
  })
  const [isLoading, setIsLoading] = useState(false)
  const isLoadingRef = useRef(false)

  useEffect(() => {
    saveMessages(messages)
  }, [messages])

  const handleSubmit = useCallback(async (query) => {
    const trimmed = query.trim()
    if (!trimmed || isLoadingRef.current) return

    isLoadingRef.current = true
    setIsLoading(true)
    setMessages((current) => [
      ...current,
      createMessage({ role: 'user', content: trimmed }),
    ])

    try {
      const answer = await sendChatQuery(trimmed)
      setMessages((current) => [
        ...current,
        createMessage({ role: 'assistant', content: answer }),
      ])
    } catch (error) {
      setMessages((current) => [
        ...current,
        createMessage({
          role: 'assistant',
          isError: true,
          content:
            error instanceof Error
              ? error.message
              : 'Something went wrong. Please try again.',
        }),
      ])
    } finally {
      isLoadingRef.current = false
      setIsLoading(false)
    }
  }, [])

  return (
    <div className="app-shell">
      <Header />
      <main className="app-main">
        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          onExampleSelect={handleSubmit}
        />
        <SearchInput onSubmit={handleSubmit} disabled={isLoading} />
      </main>
    </div>
  )
}
