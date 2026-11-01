import './LoadingIndicator.css'

export default function LoadingIndicator({ message = 'Thinking…' }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="loading__label">AI</span>
      <div className="loading__card">
        <span className="loading__dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <p className="loading__text">{message}</p>
      </div>
    </div>
  )
}
