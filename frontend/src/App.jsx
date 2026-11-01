import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChatQuery } from './api/chat'
import {
  createConversation, deleteConversation, fetchConversation,
  fetchConversations, renameConversation, updateConversation, updateConversationDocuments,
} from './api/conversations'
import { fetchDocuments } from './api/documents'
import { fetchPreferences } from './api/preferences'
import ChatModeSelector from './components/ChatModeSelector'
import ChatWindow from './components/ChatWindow'
import DocumentLibrary from './components/DocumentLibrary'
import SearchInput from './components/SearchInput'
import SettingsPage from './components/SettingsPage'
import Sidebar from './components/Sidebar'
import UsageDashboard from './components/UsageDashboard'
import './App.css'

let messageSeq = 0
const ACTIVE_CONVERSATION_KEY = 'research-assistant.active-conversation'
const createMessage = (partial) => ({ id: `local-${++messageSeq}`, ...partial })
const fromServer = (records) => records.map((item) => ({
  id: String(item.id), role: item.role, content: item.content,
  mode: item.mode || 'general', status: item.status || null,
  citations: item.citations || [], webCitations: item.web_citations || [],
  researchPlan: item.research_plan || [], researchSummary: item.research_summary || null,
  evidenceConflicts: item.evidence_conflicts || [], presentation: item.presentation || { type: 'standard' },
  attachments: item.attachments || [],
}))

export default function App() {
  const [view, setView] = useState('chat')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [conversations, setConversations] = useState([])
  const [conversationSearch, setConversationSearch] = useState('')
  const [conversationId, setConversationId] = useState(null)
  const [messages, setMessages] = useState([])
  const [documents, setDocuments] = useState([])
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([])
  const [chatMode, setChatMode] = useState('general')
  const [researchMode, setResearchMode] = useState('standard')
  const [preferences, setPreferences] = useState({ response_language: 'auto', response_depth: 'auto', default_mode: 'general', theme: 'dark' })
  const [isLoading, setIsLoading] = useState(false)
  const loadingRef = useRef(false)
  const conversationRef = useRef(null)
  const abortRef = useRef(null)
  const restoredConversationRef = useRef(false)

  const loadConversations = useCallback(async () => {
    const result = await fetchConversations(conversationSearch)
    setConversations(result.items)
    if (!restoredConversationRef.current && !conversationRef.current && result.items.length) {
      restoredConversationRef.current = true
      const savedId = window.localStorage.getItem(ACTIVE_CONVERSATION_KEY)
      const target = result.items.find((item) => item.id === savedId) || result.items[0]
      const detail = await fetchConversation(target.id)
      conversationRef.current = target.id
      setConversationId(target.id)
      setMessages(fromServer(detail.messages))
      setSelectedDocumentIds(detail.document_ids || [])
      setChatMode(detail.mode === 'documents' ? 'documents' : 'general')
      setResearchMode(detail.mode === 'deep' ? 'deep' : 'standard')
    }
  }, [conversationSearch])

  useEffect(() => { const timer = window.setTimeout(() => { void loadConversations() }, 180); return () => window.clearTimeout(timer) }, [loadConversations])
  useEffect(() => { fetchDocuments().then(setDocuments).catch(() => {}); fetchPreferences().then(applyPreferences).catch(() => {}) }, [])
  useEffect(() => { conversationRef.current = conversationId }, [conversationId])

  function applyPreferences(next) {
    setPreferences(next)
    document.documentElement.dataset.theme = next.theme
    if (!conversationRef.current) {
      if (next.default_mode === 'documents') setChatMode('documents')
      if (next.default_mode === 'deep') { setChatMode('general'); setResearchMode('deep') }
    }
  }

  async function openConversation(id) {
    if (loadingRef.current) abortRef.current?.abort()
    const detail = await fetchConversation(id)
    conversationRef.current = id; setConversationId(id)
    window.localStorage.setItem(ACTIVE_CONVERSATION_KEY, id)
    setMessages(fromServer(detail.messages)); setSelectedDocumentIds(detail.document_ids || [])
    setChatMode(detail.mode === 'documents' ? 'documents' : 'general')
    setResearchMode(detail.mode === 'deep' ? 'deep' : 'standard'); setView('chat')
  }

  async function newChat() {
    if (loadingRef.current) abortRef.current?.abort()
    const mode = researchMode === 'deep' ? 'deep' : chatMode
    const item = await createConversation(mode)
    setConversations((current) => [item, ...current]); conversationRef.current = item.id
    window.localStorage.setItem(ACTIVE_CONVERSATION_KEY, item.id)
    setConversationId(item.id); setMessages([]); setSelectedDocumentIds([]); setView('chat')
  }

  async function handleRename(item) {
    const title = window.prompt('Rename conversation', item.title)
    if (!title?.trim()) return
    const updated = await renameConversation(item.id, title.trim())
    setConversations((current) => current.map((entry) => entry.id === item.id ? updated : entry))
  }
  async function handleDelete(item) {
    if (!window.confirm(`Delete “${item.title}”?`)) return
    await deleteConversation(item.id)
    setConversations((current) => current.filter((entry) => entry.id !== item.id))
    if (conversationRef.current === item.id) {
      window.localStorage.removeItem(ACTIVE_CONVERSATION_KEY)
      conversationRef.current = null; setConversationId(null); setMessages([])
    }
  }

  const submit = useCallback(async (query) => {
    const trimmed = query.trim()
    if (!trimmed || loadingRef.current) return false
    loadingRef.current = true; setIsLoading(true)
    const controller = new AbortController(); abortRef.current = controller
    const requestMode = chatMode
    const ids = requestMode === 'documents' ? selectedDocumentIds : []
    setMessages((current) => [...current, createMessage({ role: 'user', content: trimmed, mode: requestMode, attachments: documents.filter((item) => ids.includes(item.id)).map((item) => ({ document_id: item.id, filename: item.original_filename, file_size: item.file_size, indexing_status: item.indexing_status })) })])
    let assistantId = null
    const upsert = (partial) => {
      if (!assistantId) { const item = createMessage({ role: 'assistant', content: '', ...partial }); assistantId = item.id; setMessages((current) => [...current, item]); return }
      setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, ...partial } : item))
    }
    try {
      await streamChatQuery(trimmed, (text) => upsert({ content: text, mode: requestMode }), {
        conversationId: conversationRef.current, mode: requestMode, documentIds: ids,
        researchMode, responseDepth: preferences.response_depth,
        responseLanguage: preferences.response_language, signal: controller.signal,
        onConversationId: (id) => { conversationRef.current = id; setConversationId(id); window.localStorage.setItem(ACTIVE_CONVERSATION_KEY, id) },
        onMetadata: (metadata) => upsert({ mode: metadata.mode, status: metadata.status, citations: metadata.citations, webCitations: metadata.webCitations, researchPlan: metadata.researchPlan, researchSummary: metadata.researchSummary, evidenceConflicts: metadata.evidenceConflicts, presentation: metadata.presentation }),
      })
      await loadConversations(); return true
    } catch (error) {
      if (error?.name === 'AbortError') upsert({ content: 'Generation stopped.', isError: true })
      else upsert({ content: error instanceof Error ? error.message : 'Request failed.', isError: true })
      return false
    } finally { loadingRef.current = false; setIsLoading(false); abortRef.current = null }
  }, [chatMode, documents, loadConversations, preferences, researchMode, selectedDocumentIds])

  const documentsChanged = useCallback((items) => {
    setDocuments((current) => [
      ...items,
      ...current.filter((old) => !items.some((item) => item.id === old.id)),
    ])
  }, [])

  async function selectionChanged(ids) {
    setSelectedDocumentIds(ids)
    if (conversationRef.current) await updateConversationDocuments(conversationRef.current, ids)
  }
  async function selectChatMode(mode, nextResearchMode = 'standard') {
    setChatMode(mode)
    setResearchMode(nextResearchMode)
    if (!conversationRef.current) return
    const persistentMode = mode === 'documents' ? 'documents' : nextResearchMode === 'deep' ? 'deep' : 'general'
    const updated = await updateConversation(conversationRef.current, { mode: persistentMode })
    setConversations((current) => current.map((item) => item.id === updated.id ? updated : item))
  }
  function selectView(next) {
    setView(next === 'research' ? 'chat' : next)
    if (next === 'research') { setChatMode('general'); setResearchMode('deep') }
  }

  return (
    <div className="app-shell">
      <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((value) => !value)} view={view} onView={selectView} conversations={conversations} activeId={conversationId} onSelectConversation={openConversation} onNewChat={newChat} onRename={handleRename} onDelete={handleDelete} search={conversationSearch} onSearch={setConversationSearch} />
      <main className="workspace">
        {view === 'documents' ? <DocumentLibrary onDocumentsChanged={documentsChanged} /> : null}
        {view === 'usage' ? <UsageDashboard /> : null}
        {view === 'settings' ? <SettingsPage onPreferences={applyPreferences} /> : null}
        {view === 'chat' ? <div className="chat-workspace"><header className="workspace__top"><div><span>{researchMode === 'deep' ? 'Deep Research' : chatMode === 'documents' ? 'Document Chat' : 'General Chat'}</span><small>{conversationId ? 'Persistent conversation' : 'Start a new conversation'}</small></div>{isLoading ? <button type="button" onClick={() => abortRef.current?.abort()}>Stop generating</button> : null}</header><ChatModeSelector mode={chatMode} researchMode={researchMode} selectedCount={selectedDocumentIds.length} onSelect={(mode, nextResearchMode) => void selectChatMode(mode, nextResearchMode)} disabled={isLoading} /><ChatWindow messages={messages} isLoading={isLoading} onExampleSelect={submit} mode={chatMode} researchMode={researchMode} /><SearchInput onSubmit={submit} onStop={() => abortRef.current?.abort()} disabled={isLoading} documents={documents} attachedDocumentIds={selectedDocumentIds} onAttachDocument={(id) => { void selectChatMode('documents', 'standard'); void selectionChanged([...new Set([...selectedDocumentIds, id])]) }} onRemoveDocument={(id) => void selectionChanged(selectedDocumentIds.filter((value) => value !== id))} onDocumentUpsert={(document) => setDocuments((current) => [document, ...current.filter((item) => item.id !== document.id)])} /></div> : null}
      </main>
    </div>
  )
}
