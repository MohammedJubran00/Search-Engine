import { useCallback, useEffect, useState } from 'react'
import { fetchUsageMetrics } from '../api/metrics'
import './UsageDashboard.css'

function Metric({ label, value, note }) { return <div className="usage__metric"><dt>{label}</dt><dd>{value}</dd>{note ? <small>{note}</small> : null}</div> }

export default function UsageDashboard() {
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState('')
  const load = useCallback(async () => { try { setMetrics(await fetchUsageMetrics()); setError('') } catch (requestError) { setError(requestError instanceof Error ? requestError.message : 'Could not load usage.') } }, [])
  // External telemetry synchronization intentionally updates component state.
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { void load(); const timer = window.setInterval(load, 3000); return () => window.clearInterval(timer) }, [load])
  const maxDaily = Math.max(1, ...(metrics?.daily_usage || []).map((item) => item.requests))

  return (
    <section className="usage usage--page" aria-label="Private usage dashboard">
      <header className="view-heading"><div><span>Persistent telemetry</span><h1>Usage & Analytics</h1><p>Provider-reported values are exact; unavailable values remain zero rather than being fabricated.</p></div><button type="button" onClick={load}>Refresh</button></header>
      {error ? <p className="view-error">{error}</p> : null}
      {!metrics ? <p>Loading usage…</p> : <>
        <dl className="usage__grid">
          <Metric label="Total API requests" value={metrics.request_count} />
          <Metric label="Successful" value={metrics.successful_requests} />
          <Metric label="Failed" value={metrics.failed_requests} />
          <Metric label="Average latency" value={`${metrics.average_response_seconds}s`} />
          <Metric label="Input tokens" value={metrics.input_tokens} note="Provider reported" />
          <Metric label="Output tokens" value={metrics.output_tokens} note="Provider reported" />
          <Metric label="Total tokens" value={metrics.total_tokens} />
          <Metric label="Embedding tokens" value={metrics.embedding_tokens} note="0 when provider omits metadata" />
          <Metric label="Gemini generation" value={metrics.gemini_generation_requests} />
          <Metric label="Gemini embeddings" value={metrics.gemini_embedding_requests} />
          <Metric label="Tavily searches" value={metrics.tavily_searches} />
          <Metric label="Estimated cost" value={`$${metrics.estimated_cost_usd}`} note="No pricing configured; not fabricated" />
        </dl>
        <section className="usage__chart"><h2>Daily requests</h2><div>{metrics.daily_usage.map((item) => <div key={item.date} className="usage__bar-row"><span>{item.date}</span><i style={{ width: `${Math.max(3, item.requests / maxDaily * 100)}%` }} /><strong>{item.requests}</strong></div>)}</div>{!metrics.daily_usage.length ? <p>No recorded usage yet.</p> : null}</section>
        <p className="usage__note">Stored in PostgreSQL and isolated by authenticated user. Dashboard refreshes every three seconds. Provider retries are represented by provider request counts, while platform requests are counted once.</p>
      </>}
    </section>
  )
}
