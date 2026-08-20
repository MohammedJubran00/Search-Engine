import Markdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import './MessageBubble.css'

function isSafeHref(href) {
  if (!href) return false
  try {
    const url = new URL(href, window.location.origin)
    return url.protocol === 'http:' || url.protocol === 'https:' || url.protocol === 'mailto:'
  } catch {
    return false
  }
}

const markdownComponents = {
  a({ href, children }) {
    if (!isSafeHref(href)) {
      return <span>{children}</span>
    }

    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    )
  },
}

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const className = [
    'message',
    isUser ? 'message--user' : 'message--assistant',
    message.isError ? 'message--error' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <article className={className}>
      <span className="message__label">{isUser ? 'You' : message.isError ? 'Error' : 'AI'}</span>
      <div className="message__body">
        {isUser || message.isError ? (
          <p className="message__plain">{message.content}</p>
        ) : (
          <div className="message__markdown">
            <Markdown
              remarkPlugins={[remarkGfm, remarkBreaks]}
              components={markdownComponents}
            >
              {message.content}
            </Markdown>
          </div>
        )}
      </div>
    </article>
  )
}
