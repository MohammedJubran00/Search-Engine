import './ChatModeSelector.css'

export default function ChatModeSelector({
  mode,
  researchMode,
  selectedCount,
  onSelect,
  disabled,
}) {
  return (
    <section className="chat-mode" aria-label="Chat mode">
      <div className="chat-mode__options">
        <button
          type="button"
          className={mode === 'general' && researchMode === 'standard' ? 'chat-mode__option chat-mode__option--active' : 'chat-mode__option'}
          aria-pressed={mode === 'general' && researchMode === 'standard'}
          disabled={disabled}
          onClick={() => onSelect('general', 'standard')}
        >
          General Chat
        </button>
        <button
          type="button"
          className={mode === 'documents' ? 'chat-mode__option chat-mode__option--active' : 'chat-mode__option'}
          aria-pressed={mode === 'documents'}
          disabled={disabled}
          onClick={() => onSelect('documents', 'standard')}
        >
          Document Chat
        </button>
        <button
          type="button"
          className={mode === 'general' && researchMode === 'deep' ? 'chat-mode__option chat-mode__option--active' : 'chat-mode__option'}
          aria-pressed={mode === 'general' && researchMode === 'deep'}
          disabled={disabled}
          title="Plans several bounded web research questions and may use more quota."
          onClick={() => onSelect('general', researchMode === 'deep' ? 'standard' : 'deep')}
        >
          Deep Research
        </button>
      </div>
      <p>
        {mode === 'documents'
          ? selectedCount
            ? `${selectedCount} document${selectedCount === 1 ? '' : 's'} selected. Readiness is shown on each attachment.`
            : 'Using all of your indexed documents.'
          : researchMode === 'deep'
            ? 'Creates a bounded research plan and may use more Gemini and Tavily quota.'
            : 'Uses the lightweight Gemini, LangGraph, and web-search flow.'}
      </p>
    </section>
  )
}
