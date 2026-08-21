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
  h1({ children }) {
    return <h1>{children}</h1>
  },
  h2({ children }) {
    return <h2>{children}</h2>
  },
  h3({ children }) {
    return <h3>{children}</h3>
  },
  ul({ children }) {
    return <ul>{children}</ul>
  },
  ol({ children }) {
    return <ol>{children}</ol>
  },
  li({ children }) {
    return <li>{children}</li>
  },
  table({ children }) {
    return (
      <div className="message__table-wrap">
        <table>{children}</table>
      </div>
    )
  },
  thead({ children }) {
    return <thead>{children}</thead>
  },
  tbody({ children }) {
    return <tbody>{children}</tbody>
  },
  tr({ children }) {
    return <tr>{children}</tr>
  },
  th({ children }) {
    return <th>{children}</th>
  },
  td({ children }) {
    return <td>{children}</td>
  },
  pre({ children }) {
    return <pre>{children}</pre>
  },
  code({ className, children }) {
    return <code className={className}>{children}</code>
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
