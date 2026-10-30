import Markdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { formatDocumentBytes } from '../api/documents'
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
      {isUser && Array.isArray(message.attachments) && message.attachments.length ? (
        <div className="message__attachments" aria-label="Attached documents">
          {message.attachments.map((attachment) => (
            <div key={attachment.document_id} className="message__attachment">
              <span>{attachment.filename.split('.').pop()?.toUpperCase() || 'FILE'}</span>
              <div>
                <strong>{attachment.filename}</strong>
                <small>
                  {formatDocumentBytes(attachment.file_size)} ·{' '}
                  {attachment.indexing_status === 'completed' ? 'Indexed' : attachment.indexing_status}
                </small>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {!message.isError && message.mode === 'documents' ? (
        <div className="message__grounding">
          <span className="message__mode">
            {message.status === 'insufficient_evidence'
              ? 'Insufficient document evidence'
              : 'Document-grounded'}
          </span>
          {!isUser && Array.isArray(message.citations) && message.citations.length ? (
            <ol className="message__citations" aria-label="Document citations">
              {message.citations.map((citation) => (
                <li key={`${citation.label}-${citation.chunk_id}`}>
                  <strong>[{citation.label}] {citation.filename}</strong>
                  <span>
                    {citation.page_number == null ? 'Page unavailable' : `Page ${citation.page_number}`}
                  </span>
                  {citation.evidence_excerpt ? (
                    <details>
                      <summary>View evidence excerpt</summary>
                      <q>{citation.evidence_excerpt}</q>
                    </details>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : null}
        </div>
      ) : null}
      {!isUser && !message.isError && Array.isArray(message.webCitations) && message.webCitations.length ? (
        <div className="message__web-sources">
          <span className="message__mode">Web sources</span>
          <ol aria-label="Web sources">
            {message.webCitations.map((source) => (
              <li key={source.url}>
                <a href={source.url} target="_blank" rel="noopener noreferrer">
                  {source.title}
                </a>
                <small>
                  {source.publisher || 'Publisher unavailable'} · {source.source_type || 'unspecified source type'}
                </small>
                {source.published_date ? <small>Published {source.published_date}</small> : null}
                {source.evidence_excerpt ? (
                  <details>
                    <summary>View evidence excerpt</summary>
                    <q>{source.evidence_excerpt}</q>
                  </details>
                ) : null}
                {Array.isArray(source.quality_notes) && source.quality_notes.length ? (
                  <details>
                    <summary>Source quality notes</summary>
                    <ul>{source.quality_notes.map((note) => <li key={note}>{note}</li>)}</ul>
                  </details>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {!isUser && !message.isError && Array.isArray(message.researchPlan) && message.researchPlan.length ? (
        <details className="message__research-plan">
          <summary>Research plan</summary>
          <ol>
            {message.researchPlan.map((step) => <li key={step}>{step}</li>)}
          </ol>
        </details>
      ) : null}
      {!isUser && !message.isError && message.researchSummary ? (
        <p className="message__research-summary">
          {message.researchSummary.search_count} web search{message.researchSummary.search_count === 1 ? '' : 'es'}
          {' · '}{String(message.researchSummary.termination_reason).replaceAll('_', ' ')}
          {message.researchSummary.search_failures
            ? ` · ${message.researchSummary.search_failures} failed`
            : ''}
        </p>
      ) : null}
      {!isUser && !message.isError && Array.isArray(message.evidenceConflicts) && message.evidenceConflicts.length ? (
        <section className="message__conflicts" aria-label="Evidence comparison">
          <strong>Evidence comparison</strong>
          {message.evidenceConflicts.map((relationship, index) => (
            <details key={`${relationship.status}-${index}`}>
              <summary>{relationship.status.replaceAll('_', ' ')}</summary>
              <p>{relationship.reason}</p>
              <ul>
                {relationship.claims.map((claim) => (
                  <li key={`${claim.source_url}-${claim.value}`}>
                    <a href={claim.source_url} target="_blank" rel="noopener noreferrer">
                      {claim.source_title || claim.source_url}
                    </a>
                    : {claim.currency ? `${claim.currency} ` : ''}{claim.value}{claim.unit ? ` ${claim.unit}` : ''}
                    {claim.years?.length ? ` (${claim.years.join(', ')})` : ''}
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </section>
      ) : null}
    </article>
  )
}
