import { useCallback, useRef, useState } from 'react'
import { sendChatQuery } from './api/chat'
import ChatWindow from './components/ChatWindow'
import Header from './components/Header'
import SearchInput from './components/SearchInput'
import './App.css'

let messageSeq = 0

function createMessage(partial) {
  messageSeq += 1
  return {
    id: `msg-${messageSeq}`,
    ...partial,
  }
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const isLoadingRef = useRef(false)

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
