import { useCallback, useEffect, useState } from 'react'
import { fetchUsageMetrics } from '../api/metrics'
import './UsageDashboard.css'

function Metric({ label, value, suffix = '' }) {
  return (
    <div className="usage__metric">
      <dt>{label}</dt>
      <dd>{value}{suffix}</dd>
    </div>
  )
}

export default function UsageDashboard() {
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setMetrics(await fetchUsageMetrics())
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not load usage.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchUsageMetrics()
      .then((payload) => {
        if (!cancelled) setMetrics(payload)
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : 'Could not load usage.')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  return (
    <section className="usage" aria-label="Private usage dashboard">
      <div className="usage__heading">
        <div>
          <h2>Private usage</h2>
          <p>Content-free operational totals for your account in this server process.</p>
        </div>
        <button type="button" onClick={load} disabled={loading}>Refresh</button>
      </div>
      {loading && !metrics ? <p className="usage__state">Loading usage…</p> : null}
      {error ? <p className="usage__state usage__state--error">{error}</p> : null}
      {metrics ? (
        <>
          <dl className="usage__grid">
            <Metric label="Requests" value={metrics.request_count} />
            <Metric label="Today" value={`${metrics.daily_request_count} / ${metrics.daily_request_limit}`} />
            <Metric label="Avg response" value={metrics.average_response_seconds} suffix="s" />
            <Metric label="Avg retrieval" value={metrics.average_retrieval_seconds} suffix="s" />
            <Metric label="Avg web search" value={metrics.average_tavily_seconds} suffix="s" />
            <Metric label="Avg searches" value={metrics.average_searches} />
            <Metric label="Avg sources" value={metrics.average_sources} />
            <Metric label="Input tokens" value={metrics.input_tokens} />
            <Metric label="Output tokens" value={metrics.output_tokens} />
            <Metric label="Embedding jobs" value={metrics.embedding_requests} />
            <Metric label="Errors" value={metrics.error_count} />
            <Metric label="Quota errors" value={metrics.quota_error_count} />
          </dl>
          <p className="usage__note">
            Modes: {metrics.modes.general} general, {metrics.modes.documents} document,
            {' '}{metrics.modes.deep_research} deep research. Token totals appear only when a
            provider reports them. Metrics are bounded, process-local, and reset on restart.
          </p>
        </>
      ) : null}
    </section>
  )
}
