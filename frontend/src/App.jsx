import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchLatestConversation, streamChatQuery } from './api/chat'
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

function messagesFromServer(records) {
  return records
    .filter(
      (item) =>
        item &&
        (item.role === 'user' || item.role === 'assistant') &&
        typeof item.content === 'string',
    )
    .map((item) => ({
      id: String(item.id),
      role: item.role,
      content: item.content,
    }))
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const isLoadingRef = useRef(false)
  const conversationIdRef = useRef(null)

  useEffect(() => {
    conversationIdRef.current = conversationId
  }, [conversationId])

  useEffect(() => {
    let cancelled = false

    fetchLatestConversation()
      .then((latest) => {
        if (cancelled) return
        if (latest.conversationId) {
          conversationIdRef.current = latest.conversationId
          setConversationId(latest.conversationId)
        }
        if (latest.messages.length) {
          setMessages(messagesFromServer(latest.messages))
        }
      })
      .catch(() => {
        // 401 already redirects. Other errors leave an empty chat.
      })

    return () => {
      cancelled = true
    }
  }, [])

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
      }, {
        conversationId: conversationIdRef.current,
        onConversationId: (id) => {
          conversationIdRef.current = id
          setConversationId(id)
        },
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
