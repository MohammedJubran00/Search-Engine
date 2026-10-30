import './ChatModeSelector.css'

export default function ChatModeSelector({ mode, selectedCount, onChange, disabled }) {
  return (
    <section className="chat-mode" aria-label="Chat mode">
      <div className="chat-mode__options">
        <button
          type="button"
          className={mode === 'general' ? 'chat-mode__option chat-mode__option--active' : 'chat-mode__option'}
          aria-pressed={mode === 'general'}
          disabled={disabled}
          onClick={() => onChange('general')}
        >
          General Chat
        </button>
        <button
          type="button"
          className={mode === 'documents' ? 'chat-mode__option chat-mode__option--active' : 'chat-mode__option'}
          aria-pressed={mode === 'documents'}
          disabled={disabled}
          onClick={() => onChange('documents')}
        >
          Document Chat
        </button>
      </div>
      <p>
        {mode === 'documents'
          ? selectedCount
            ? `${selectedCount} indexed document${selectedCount === 1 ? '' : 's'} selected.`
            : 'Using all of your indexed documents.'
          : 'Uses the existing Gemini, LangGraph, and web-search flow.'}
      </p>
    </section>
  )
}
