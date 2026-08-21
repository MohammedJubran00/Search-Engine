import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChatQuery } from './api/chat'
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
    const userMessage = createMessage({ role: 'user', content: trimmed })
    setMessages((current) => [...current, userMessage])

    let assistantId = null

    function upsertAssistant(partial) {
      if (!assistantId) {
        const assistantMessage = createMessage({
          role: 'assistant',
          content: '',
          ...partial,
        })
        assistantId = assistantMessage.id
        setMessages((current) => [...current, assistantMessage])
        return
      }

      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId ? { ...message, ...partial } : message,
        ),
      )
    }

    try {
      await streamChatQuery(trimmed, (fullText) => {
        upsertAssistant({ content: fullText, isError: false })
      })
    } catch (error) {
      upsertAssistant({
        isError: true,
        content:
          error instanceof Error
            ? error.message
            : 'Something went wrong. Please try again.',
      })
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
