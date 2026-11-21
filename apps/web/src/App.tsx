import { FormEvent, useEffect, useState } from 'react'
import { ChatResult, LoginResult, Role, request } from './api'

type AuthState = LoginResult & { username: string }
type Message = { sender: 'employee' | 'agent'; content: string; result?: ChatResult }
type DashboardData = {
  summary: Record<string, number>
  resolution_by_intent: Record<string, number>
  tool_outcomes: { success: number; failure: number }
  confidence_distribution: Record<string, number>
  top_unresolved_intents: { intent: string; count: number }[]
  daily_trend: { date: string; conversations: number; resolved: number; escalated: number }[]
  latest_escalated_tickets: { external_id: string; issue: string; intent: string; created_at: string; session_id: string }[]
}

const pct = (value = 0) => `${(value * 100).toFixed(1)}%`
const usd = (value = 0) => `$${value.toFixed(4)}`
const label = (value: string) => value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())

function Login({ onLogin }: { onLogin: (auth: AuthState) => void }) {
  const [username, setUsername] = useState('employee01')
  const [password, setPassword] = useState('demo123')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const auth = await request<LoginResult>('/api/auth/login', undefined, { method: 'POST', body: JSON.stringify({ username, password }) })
      onLogin({ ...auth, username })
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  return <main className="login-shell">
    <section className="brand-panel">
      <div className="brand-mark">N</div>
      <p className="eyebrow">Northstar digital workplace</p>
      <h1>Support that resolves, safely.</h1>
      <p className="brand-copy">Approved knowledge, permission-aware actions, and a complete operational trail—every time.</p>
      <div className="trust-row"><span>Grounded answers</span><span>Audited actions</span><span>Human escalation</span></div>
    </section>
    <section className="login-panel">
      <form className="login-card" onSubmit={submit}>
        <p className="eyebrow accent">Secure service desk</p><h2>Welcome back</h2>
        <p className="muted">Use your demo workplace identity.</p>
        <label>Username<input aria-label="Username" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" /></label>
        <label>Password<input aria-label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" /></label>
        {error && <div className="error" role="alert">{error}</div>}
        <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in securely'}</button>
        <div className="demo-users"><b>Demo access</b><span>Employee: employee01 / demo123</span><span>Operations: support / support123</span></div>
      </form>
    </section>
  </main>
}

function Shell({ auth, children, onLogout, view, setView }: { auth: AuthState; children: React.ReactNode; onLogout: () => void; view: string; setView: (v: string) => void }) {
  const ops = auth.role !== 'employee'
  return <div className="app-shell">
    <aside><div className="logo-row"><div className="brand-mark small">N</div><div><b>Northstar</b><span>Service Desk</span></div></div>
      <nav><button className={view === 'support' ? 'active' : ''} onClick={() => setView('support')}><span>◎</span>Employee support</button>{ops && <button className={view === 'dashboard' ? 'active' : ''} onClick={() => setView('dashboard')}><span>▦</span>Operations</button>}</nav>
      <div className="side-status"><span className="status-dot" />All systems operational<small>Grounded AI mode</small></div>
      <button className="profile" onClick={onLogout}><span className="avatar">{auth.display_name[0]}</span><span><b>{auth.display_name}</b><small>{label(auth.role)}</small></span><span>↗</span></button>
    </aside>
    <section className="workspace">{children}</section>
  </div>
}

function Support({ auth }: { auth: AuthState }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = [...messages].reverse().find(m => m.result?.requires_confirmation)?.result

  async function send(event?: FormEvent) {
    event?.preventDefault(); if (!draft.trim() || busy) return
    const content = draft.trim(); setDraft(''); setMessages(list => [...list, { sender: 'employee', content }]); setBusy(true)
    try {
      const result = await request<ChatResult>('/api/chat', auth.access_token, { method: 'POST', body: JSON.stringify({ message: content }) })
      setMessages(list => [...list, { sender: 'agent', content: result.reply, result }])
    } catch (err) { setMessages(list => [...list, { sender: 'agent', content: `I couldn't process that request: ${(err as Error).message}` }]) } finally { setBusy(false) }
  }
  async function confirm(approved: boolean) {
    if (!pending) return; setBusy(true)
    try {
      const result = await request<ChatResult>(`/api/chat/${pending.session_id}/confirm`, auth.access_token, { method: 'POST', body: JSON.stringify({ approved }) })
      setMessages(list => [...list, { sender: 'agent', content: result.reply, result }])
    } catch (err) { setMessages(list => [...list, { sender: 'agent', content: (err as Error).message }]) } finally { setBusy(false) }
  }
  return <div className="support-page"><header><div><p className="eyebrow accent">Employee support</p><h1>How can I help today?</h1><p>Describe the issue in your own words. I’ll use approved company guidance.</p></div><span className="secure-pill">● Secure session</span></header>
    <div className="chat-card" aria-live="polite">
      {!messages.length && <div className="empty-chat"><div className="agent-orb">✦</div><h2>Hi {auth.display_name.split(' ')[1] || auth.display_name}</h2><p>Choose a common task or tell me what’s going wrong.</p><div className="quick-grid">{['Reset my password', 'Unlock my account', 'VPN is not connecting', 'Is email down?'].map(text => <button key={text} onClick={() => setDraft(text)}>{text}<span>→</span></button>)}</div></div>}
      <div className="messages">{messages.map((message, index) => <article key={index} className={`message ${message.sender}`}><div className="message-avatar">{message.sender === 'agent' ? '✦' : auth.display_name[0]}</div><div><small>{message.sender === 'agent' ? 'Northstar agent' : 'You'}</small><p>{message.content}</p>{message.result && <ResultDetails result={message.result} />}</div></article>)}{busy && <div className="thinking"><i /><i /><i /> Checking approved guidance…</div>}</div>
      {pending && !messages.slice(messages.findIndex(m => m.result?.session_id === pending.session_id) + 1).some(m => m.result?.session_id === pending.session_id) && <div className="confirm-bar"><div><b>Confirmation required</b><span>{pending.pending_action?.description}</span></div><button className="secondary" onClick={() => confirm(false)}>Cancel</button><button className="primary compact" onClick={() => confirm(true)}>Confirm action</button></div>}
      <form className="composer" onSubmit={send}><textarea aria-label="Support request" value={draft} onChange={e => setDraft(e.target.value)} placeholder="Describe your IT issue…" maxLength={4000} /><button className="send" aria-label="Send request" disabled={busy || !draft.trim()}>↑</button><small>Actions that change your account always require confirmation.</small></form>
    </div>
  </div>
}

function ResultDetails({ result }: { result: ChatResult }) {
  return <div className="result-details"><div className="result-meta"><span className={`outcome ${result.status}`}>{label(result.status)}</span><span>{label(result.intent)}</span><span>{Math.round(result.confidence * 100)}% confidence</span>{result.ticket_id && <span className="ticket">{result.ticket_id}</span>}</div>{result.citations.length > 0 && <details><summary>{result.citations.length} approved source{result.citations.length > 1 ? 's' : ''}</summary>{result.citations.map(c => <div className="citation" key={c.document_id}><b>{c.title}</b><p>{c.excerpt}</p><span>{Math.round(c.score * 100)}% relevance · {c.document_id}</span></div>)}</details>}</div>
}

function Dashboard({ auth }: { auth: AuthState }) {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')
  const [trace, setTrace] = useState<any>(null)
  useEffect(() => { request<DashboardData>('/api/dashboard', auth.access_token).then(setData).catch(e => setError(e.message)) }, [auth.access_token])
  async function openTrace(session: string) { setTrace(await request(`/api/sessions/${session}/trace`, auth.access_token)) }
  if (error) return <div className="error page-error">{error}</div>
  if (!data) return <div className="loader">Loading operational metrics…</div>
  const cards = [
    ['Strict deflection', pct(data.summary.strict_deflection_rate), 'Verified, no replay-window reopen'],
    ['Automation rate', pct(data.summary.loose_automation_rate), 'Resolved without a human'],
    ['Escalation rate', pct(data.summary.escalation_rate), 'Diagnostic ticket created'],
    ['Cost / resolved', usd(data.summary.cost_per_resolved_request_usd), 'Model and tool usage'],
  ]
  const maxTrend = Math.max(...data.daily_trend.map(d => d.conversations), 1)
  return <div className="dashboard-page"><header className="dash-header"><div><p className="eyebrow accent">Operations cockpit</p><h1>Service desk performance</h1><p>{data.summary.total_conversations} conversations in the current demo dataset</p></div><button className="secondary" onClick={() => location.reload()}>Refresh metrics</button></header>
    <div className="metric-grid">{cards.map(([name, value, note]) => <article key={name}><span>{name}</span><strong>{value}</strong><small>{note}</small></article>)}</div>
    <div className="dashboard-grid"><section className="panel wide"><div className="panel-title"><div><h2>Daily outcomes</h2><p>Conversation volume and disposition</p></div><div className="legend"><span className="teal">Resolved</span><span className="coral">Escalated</span></div></div><div className="bars">{data.daily_trend.map(day => <div className="bar-group" key={day.date}><div className="stack" style={{ height: `${Math.max(8, day.conversations / maxTrend * 170)}px` }}><i className="resolved" style={{ flex: day.resolved || .1 }} /><i className="escalated" style={{ flex: day.escalated || .1 }} /></div><small>{day.date.slice(5)}</small></div>)}</div></section>
      <section className="panel"><div className="panel-title"><div><h2>Tool reliability</h2><p>Allowlisted executions</p></div></div><div className="donut" style={{ '--success': `${data.tool_outcomes.success / Math.max(1, data.tool_outcomes.success + data.tool_outcomes.failure) * 360}deg` } as React.CSSProperties}><div><strong>{data.tool_outcomes.success + data.tool_outcomes.failure}</strong><span>calls</span></div></div><div className="tool-key"><span><i className="ok" />Successful <b>{data.tool_outcomes.success}</b></span><span><i className="bad" />Failed <b>{data.tool_outcomes.failure}</b></span></div></section>
      <section className="panel"><div className="panel-title"><div><h2>Resolved by intent</h2><p>Top automated categories</p></div></div><div className="intent-list">{Object.entries(data.resolution_by_intent).sort((a,b) => b[1]-a[1]).slice(0,6).map(([intent,count]) => <div key={intent}><span>{label(intent)}</span><b>{count}</b><i style={{ width: `${count / Math.max(...Object.values(data.resolution_by_intent), 1) * 100}%` }} /></div>)}</div></section>
      <section className="panel wide tickets-panel"><div className="panel-title"><div><h2>Latest escalations</h2><p>Tickets carrying complete diagnostic context</p></div></div><div className="ticket-table"><div className="table-head"><span>Ticket</span><span>Issue</span><span>Intent</span><span>Created</span><span /></div>{data.latest_escalated_tickets.slice(0,7).map(ticket => <div key={ticket.external_id}><b>{ticket.external_id}</b><span>{ticket.issue}</span><span className="tag">{label(ticket.intent)}</span><span>{new Date(ticket.created_at).toLocaleDateString()}</span><button onClick={() => openTrace(ticket.session_id)}>View trace</button></div>)}</div></section>
    </div>
    {trace && <div className="modal-backdrop" onClick={() => setTrace(null)}><section className="trace-modal" onClick={e => e.stopPropagation()}><button className="close" onClick={() => setTrace(null)}>×</button><p className="eyebrow accent">Safe operational trace</p><h2>{trace.session.id}</h2><div className="trace-summary"><span>{label(trace.session.status)}</span><span>{label(trace.session.detected_intent)}</span><span>{Math.round(trace.session.confidence*100)}% confidence</span></div><div className="timeline">{trace.states.map((event: any, index: number) => <div key={index}><i /><span><b>{label(event.state)}</b><p>{event.decision}</p><small>{event.duration_ms.toFixed(1)} ms</small></span></div>)}</div></section></div>}
  </div>
}

export default function App() {
  const [auth, setAuth] = useState<AuthState | null>(() => { try { return JSON.parse(sessionStorage.getItem('service-auth') || 'null') } catch { return null } })
  const [view, setView] = useState('support')
  function login(value: AuthState) { setAuth(value); sessionStorage.setItem('service-auth', JSON.stringify(value)); if (value.role !== 'employee') setView('dashboard') }
  function logout() { setAuth(null); sessionStorage.removeItem('service-auth') }
  if (!auth) return <Login onLogin={login} />
  return <Shell auth={auth} onLogout={logout} view={view} setView={setView}>{view === 'dashboard' && auth.role !== 'employee' ? <Dashboard auth={auth} /> : <Support auth={auth} />}</Shell>
}
