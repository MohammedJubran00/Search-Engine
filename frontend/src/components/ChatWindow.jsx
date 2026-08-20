import { useEffect, useRef } from 'react'
import LoadingIndicator from './LoadingIndicator'
import MessageBubble from './MessageBubble'
import './ChatWindow.css'

const EXAMPLE_QUERIES = [
  'Who founded OpenAI?',
  'What are the latest developments in quantum computing?',
  'Summarize the current state of renewable energy.',
]

export default function ChatWindow({ messages, isLoading, onExampleSelect }) {
  const endRef = useRef(null)
  const isEmpty = messages.length === 0 && !isLoading

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isLoading])

  return (
    <section className="chat-window" aria-live="polite">
      {isEmpty ? (
        <div className="chat-window__welcome">
          <p className="chat-window__eyebrow">Ready when you are</p>
          <h2 className="chat-window__heading">Ask a question. Get a sourced answer.</h2>
          <p className="chat-window__copy">
            The engine searches the live web, then the AI writes a clear response.
            Try one of these to get started.
          </p>
          <div className="chat-window__examples">
            {EXAMPLE_QUERIES.map((query) => (
              <button
                key={query}
                type="button"
                className="chat-window__example"
                onClick={() => onExampleSelect(query)}
              >
                {query}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="chat-window__messages">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {isLoading ? <LoadingIndicator /> : null}
          <div ref={endRef} />
        </div>
      )}
    </section>
  )
}
