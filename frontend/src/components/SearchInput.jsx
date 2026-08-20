import { useEffect, useRef, useState } from 'react'
import './SearchInput.css'

export default function SearchInput({ onSubmit, disabled }) {
  const [value, setValue] = useState('')
  const textareaRef = useRef(null)
  const canSend = value.trim().length > 0 && !disabled

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }, [value])

  useEffect(() => {
    if (!disabled) {
      textareaRef.current?.focus()
    }
  }, [disabled])

  function handleSubmit() {
    if (!canSend) return
    const query = value
    setValue('')
    onSubmit(query)
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSubmit()
    }
  }

  return (
    <form
      className="search-input"
      onSubmit={(event) => {
        event.preventDefault()
        handleSubmit()
      }}
    >
      <label className="visually-hidden" htmlFor="search-query">
        Ask a question
      </label>
      <div className="search-input__bar">
        <textarea
          id="search-query"
          ref={textareaRef}
          className="search-input__field"
          rows={1}
          value={value}
          placeholder="Ask anything…"
          autoComplete="off"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          enterKeyHint="send"
        />
        <button
          type="submit"
          className="search-input__send"
          disabled={!canSend}
          aria-label={disabled ? 'Waiting for answer' : 'Send question'}
        >
          {disabled ? (
            <span className="search-input__spinner" aria-hidden="true" />
          ) : (
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
              <path
                d="M3 9h12M10.5 4.5 15 9l-4.5 4.5"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
          <span className="search-input__send-label">{disabled ? 'Searching' : 'Search'}</span>
        </button>
      </div>
      <p className="search-input__hint">Enter to search · Shift + Enter for a new line</p>
    </form>
  )
}
