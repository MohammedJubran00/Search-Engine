import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchLatestConversation, streamChatQuery } from './api/chat'
import ChatWindow from './components/ChatWindow'
import ChatModeSelector from './components/ChatModeSelector'
import DocumentPanel from './components/DocumentPanel'
import Header from './components/Header'
import SearchInput from './components/SearchInput'
import UsageDashboard from './components/UsageDashboard'
import './App.css'

let messageSeq = 0

function nextMessageId() {
  messageSeq += 1
  return `msg-${messageSeq}`
}

function createMessage(partial) {
  return {
    id: nextMessageId(),
    ...partial,
  }
}

function messagesFromServer(records) {
  return records
    .filter(
      (item) =>
        item &&
        (item.role === 'user' || item.role === 'assistant') &&
        typeof item.content === 'string',
    )
    .map((item) => ({
      id: String(item.id),
      role: item.role,
      content: item.content,
      mode: item.mode || 'general',
      status: item.status || null,
      citations: Array.isArray(item.citations) ? item.citations : [],
      webCitations: Array.isArray(item.web_citations) ? item.web_citations : [],
      researchPlan: Array.isArray(item.research_plan) ? item.research_plan : [],
      researchSummary: item.research_summary || null,
      evidenceConflicts: Array.isArray(item.evidence_conflicts) ? item.evidence_conflicts : [],
      presentation: item.presentation || { type: 'standard' },
      attachments: Array.isArray(item.attachments) ? item.attachments : [],
    }))
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [chatMode, setChatMode] = useState('general')
  const [researchMode, setResearchMode] = useState('standard')
  const [documents, setDocuments] = useState([])
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([])
  const [metricsOpen, setMetricsOpen] = useState(false)
  const isLoadingRef = useRef(false)
  const conversationIdRef = useRef(null)

  useEffect(() => {
    conversationIdRef.current = conversationId
  }, [conversationId])

  useEffect(() => {
    let cancelled = false

    fetchLatestConversation()
      .then((latest) => {
        if (cancelled) return
        if (latest.conversationId) {
          conversationIdRef.current = latest.conversationId
          setConversationId(latest.conversationId)
        }
        if (latest.messages.length) {
          setMessages(messagesFromServer(latest.messages))
        }
      })
      .catch(() => {
        // 401 already redirects. Other errors leave an empty chat.
      })

    return () => {
      cancelled = true
    }
  }, [])

  const handleSubmit = useCallback(async (query) => {
    const trimmed = query.trim()
    if (!trimmed || isLoadingRef.current) return false

    isLoadingRef.current = true
    setIsLoading(true)
    const requestMode = chatMode
    const requestDocumentIds = requestMode === 'documents' ? selectedDocumentIds : []
    const userMessage = createMessage({
      role: 'user',
      content: trimmed,
      mode: requestMode,
      attachments: documents
        .filter((item) => requestDocumentIds.includes(item.id))
        .map((item) => ({
          document_id: item.id,
          filename: item.original_filename,
          content_type: item.content_type,
          file_size: item.file_size,
          processing_status: item.processing_status,
          indexing_status: item.indexing_status,
        })),
    })
    setMessages((current) => [...current, userMessage])

    let assistantId = null

    function upsertAssistant(partial) {
      if (!assistantId) {
        const assistantMessage = createMessage({
          role: 'assistant',
          content: '',
          ...partial,
        })
        assistantId = assistantMessage.id
        setMessages((current) => [...current, assistantMessage])
        return
      }

      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId ? { ...message, ...partial } : message,
        ),
      )
    }

    try {
      await streamChatQuery(trimmed, (fullText) => {
        upsertAssistant({ content: fullText, isError: false, mode: requestMode })
      }, {
        conversationId: conversationIdRef.current,
        mode: requestMode,
        documentIds: requestDocumentIds,
        researchMode,
        onConversationId: (id) => {
          conversationIdRef.current = id
          setConversationId(id)
        },
        onMetadata: (metadata) => {
          upsertAssistant({
            mode: metadata.mode,
            status: metadata.status,
            citations: metadata.citations,
            webCitations: metadata.webCitations,
            researchPlan: metadata.researchPlan,
            researchSummary: metadata.researchSummary,
            evidenceConflicts: metadata.evidenceConflicts,
            presentation: metadata.presentation,
          })
        },
      })
      setSelectedDocumentIds([])
      return true
    } catch (error) {
      upsertAssistant({
        isError: true,
        content:
          error instanceof Error
            ? error.message
            : 'Something went wrong. Please try again.',
      })
      return false
    } finally {
      isLoadingRef.current = false
      setIsLoading(false)
    }
  }, [chatMode, documents, researchMode, selectedDocumentIds])

  const handleModeChange = useCallback((nextMode) => {
    setChatMode(nextMode)
    if (nextMode === 'documents') setResearchMode('standard')
    if (nextMode === 'general') setSelectedDocumentIds([])
  }, [])

  const handleDocumentUpsert = useCallback((document) => {
    setDocuments((current) => [
      document,
      ...current.filter((item) => item.id !== document.id),
    ])
  }, [])

  const handleAttachDocument = useCallback((documentId) => {
    setChatMode('documents')
    setSelectedDocumentIds((current) =>
      current.includes(documentId) ? current : [...current, documentId],
    )
  }, [])

  return (
    <div className="app-shell">
      <Header
        metricsOpen={metricsOpen}
        onToggleMetrics={() => setMetricsOpen((current) => !current)}
      />
      <main className="app-main">
        {metricsOpen ? <UsageDashboard /> : null}
        <DocumentPanel
          documents={documents}
          onDocumentsChange={setDocuments}
          selectionEnabled={chatMode === 'documents'}
          selectedDocumentIds={selectedDocumentIds}
          onSelectionChange={setSelectedDocumentIds}
        />
        <ChatModeSelector
          mode={chatMode}
          researchMode={researchMode}
          selectedCount={selectedDocumentIds.length}
          onChange={handleModeChange}
          onResearchModeChange={setResearchMode}
          disabled={isLoading}
        />
        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          onExampleSelect={handleSubmit}
          mode={chatMode}
        />
        <SearchInput
          onSubmit={handleSubmit}
          disabled={isLoading}
          documents={documents}
          attachedDocumentIds={selectedDocumentIds}
          onAttachDocument={handleAttachDocument}
          onRemoveDocument={(documentId) =>
            setSelectedDocumentIds((current) => current.filter((id) => id !== documentId))
          }
          onDocumentUpsert={handleDocumentUpsert}
        />
      </main>
    </div>
  )
}
