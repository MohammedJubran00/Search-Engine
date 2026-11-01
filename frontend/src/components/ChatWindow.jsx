import { useEffect, useRef } from 'react'
import LoadingIndicator from './LoadingIndicator'
import MessageBubble from './MessageBubble'
import './ChatWindow.css'

const EXAMPLE_QUERIES = [
  'Who founded OpenAI?',
  'What are the latest developments in quantum computing?',
  'Summarize the current state of renewable energy.',
]
const DOCUMENT_EXAMPLE_QUERIES = [
  'Summarize the main goals in my documents.',
  'What risks are described in the selected documents?',
  'Which recommendations are supported by the documents?',
]

export default function ChatWindow({ messages, isLoading, onExampleSelect, mode, researchMode }) {
  const endRef = useRef(null)
  const isEmpty = messages.length === 0 && !isLoading
  const lastMessage = messages[messages.length - 1]
  const waitingForFirstToken =
    isLoading &&
    (!lastMessage || lastMessage.role !== 'assistant' || !lastMessage.content)
  const examples = mode === 'documents' ? DOCUMENT_EXAMPLE_QUERIES : EXAMPLE_QUERIES
  const progressMessage = mode === 'documents'
    ? 'Retrieving document evidence and checking citations…'
    : researchMode === 'deep'
      ? 'Planning bounded research and checking web sources…'
      : 'Researching and drafting an answer…'

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
            {mode === 'documents'
              ? 'Answers use only your indexed document evidence. They never fall back to web search.'
              : 'The engine uses the existing Gemini and web-search flow to write a clear response.'}
            {' '}Try one of these to get started.
          </p>
          <div className="chat-window__examples">
            {examples.map((query) => (
              <button
                key={query}
                type="button"
                className="chat-window__example"
                disabled={isLoading}
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
          {waitingForFirstToken ? <LoadingIndicator message={progressMessage} /> : null}
          <div ref={endRef} />
        </div>
      )}
    </section>
  )
}
