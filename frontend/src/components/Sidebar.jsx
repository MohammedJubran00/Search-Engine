import { useMemo } from 'react'
import './Sidebar.css'

function groupLabel(value) {
  const date = new Date(value)
  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const days = Math.floor((start - new Date(date.getFullYear(), date.getMonth(), date.getDate())) / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return 'Previous 7 days'
  return 'Older'
}

export default function Sidebar({
  collapsed, onToggle, view, onView, conversations, activeId,
  onSelectConversation, onNewChat, onRename, onDelete, search, onSearch,
}) {
  const grouped = useMemo(() => {
    const result = new Map()
    conversations.forEach((item) => {
      const label = groupLabel(item.updated_at)
      result.set(label, [...(result.get(label) || []), item])
    })
    return result
  }, [conversations])

  return (
    <aside className={`sidebar${collapsed ? ' sidebar--collapsed' : ''}`}>
      <div className="sidebar__brand">
        <span className="sidebar__logo">A</span>
        {!collapsed ? <strong>Arc Research</strong> : null}
        <button type="button" onClick={onToggle} aria-label="Toggle sidebar">{collapsed ? '›' : '‹'}</button>
      </div>
      <button type="button" className="sidebar__new" onClick={onNewChat}>
        <span>＋</span>{!collapsed ? 'New research chat' : null}
      </button>
      {!collapsed ? (
        <input className="sidebar__search" value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Search conversations…" />
      ) : null}
      <nav className="sidebar__nav" aria-label="Primary navigation">
        {[
          ['chat', '◫', 'General AI Chat'],
          ['documents', '▣', 'Document Library'],
          ['research', '⌁', 'Deep Research'],
          ['usage', '⌁', 'Usage & Analytics'],
          ['settings', '⚙', 'System Settings'],
        ].map(([key, icon, label]) => (
          <button key={key} type="button" className={view === key ? 'is-active' : ''} onClick={() => onView(key)} title={collapsed ? label : undefined}>
            <span>{icon}</span>{!collapsed ? label : null}
          </button>
        ))}
      </nav>
      {!collapsed ? (
        <div className="sidebar__history">
          {[...grouped].map(([label, items]) => (
            <section key={label}>
              <h2>{label}</h2>
              {items.map((item) => (
                <div key={item.id} className={`sidebar__conversation${activeId === item.id ? ' is-active' : ''}`}>
                  <button type="button" onClick={() => onSelectConversation(item.id)}>{item.title || 'New chat'}</button>
                  <div>
                    <button type="button" aria-label={`Rename ${item.title}`} onClick={() => onRename(item)}>✎</button>
                    <button type="button" aria-label={`Delete ${item.title}`} onClick={() => onDelete(item)}>×</button>
                  </div>
                </div>
              ))}
            </section>
          ))}
        </div>
      ) : null}
    </aside>
  )
}
