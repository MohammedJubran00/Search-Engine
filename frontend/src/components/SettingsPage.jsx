import { useEffect, useState } from 'react'
import { fetchCurrentUser, logout } from '../api/auth'
import { fetchPreferences, savePreferences } from '../api/preferences'
import './SettingsPage.css'

const DEFAULTS = { response_language: 'auto', response_depth: 'auto', default_mode: 'general', theme: 'dark' }

export default function SettingsPage({ onPreferences }) {
  const [user, setUser] = useState(null)
  const [values, setValues] = useState(DEFAULTS)
  const [status, setStatus] = useState('')
  useEffect(() => { Promise.all([fetchCurrentUser(), fetchPreferences()]).then(([profile, preferences]) => { setUser(profile); setValues(preferences) }).catch(() => setStatus('Could not load settings.')) }, [])

  async function save() {
    try {
      const saved = await savePreferences(values)
      setValues(saved); onPreferences?.(saved); setStatus('Settings saved.')
    } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not save settings.') }
  }
  function field(key, value) { setValues((current) => ({ ...current, [key]: value })) }

  return (
    <section className="settings-page">
      <header className="view-heading"><div><span>Personal workspace</span><h1>System Settings</h1><p>Only preferences with working application behavior are shown.</p></div></header>
      <div className="settings-grid">
        <section><h2>Account</h2><dl><dt>Name</dt><dd>{user?.full_name || 'Loading…'}</dd><dt>Email</dt><dd>{user?.email || '—'}</dd><dt>Created</dt><dd>{user?.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}</dd></dl><button className="secondary" type="button" onClick={logout}>Secure logout</button></section>
        <section><h2>AI preferences</h2><label>Preferred language<select value={values.response_language} onChange={(event) => field('response_language', event.target.value)}><option value="auto">Match conversation</option><option value="en">English</option><option value="ar">Arabic</option></select></label><label>Response depth<select value={values.response_depth} onChange={(event) => field('response_depth', event.target.value)}><option value="auto">Follow my prompt</option><option value="concise">Concise</option><option value="balanced">Balanced</option><option value="detailed">Detailed</option></select></label><label>Default mode<select value={values.default_mode} onChange={(event) => field('default_mode', event.target.value)}><option value="general">General Chat</option><option value="documents">Document Chat</option><option value="deep">Deep Research</option></select></label></section>
        <section><h2>Appearance</h2><label>Theme<select value={values.theme} onChange={(event) => field('theme', event.target.value)}><option value="dark">Dark</option><option value="light">Light</option><option value="system">System</option></select></label><p>Direction is detected per message so Arabic and English remain readable together.</p></section>
        <section><h2>Documents & privacy</h2><p>Uploads are private to your account. Indexing runs in a durable queue and sends document chunks to the configured Gemini embedding provider.</p><p>Maximum upload size: 100 MiB. API keys and tokens are never displayed here.</p></section>
      </div>
      <footer className="settings-actions"><span role="status">{status}</span><button type="button" onClick={save}>Save settings</button></footer>
    </section>
  )
}
