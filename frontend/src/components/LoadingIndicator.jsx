import './LoadingIndicator.css'

export default function LoadingIndicator() {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="loading__label">AI</span>
      <div className="loading__card">
        <span className="loading__dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <p className="loading__text">Searching the web and writing an answer…</p>
      </div>
    </div>
  )
}
