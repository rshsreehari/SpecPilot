import { useEffect, useState } from 'react'
import { deleteProvider } from '../lib/api'
import { ErrorState, LoadingState } from '../components/DataStates'
import { useAppShell } from '../context/useAppShell'
import './ApisScreen.css'

function formatDate(value: string | null): string {
  if (!value) return 'Not ingested'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

export function ApisScreen() {
  const {
    providers,
    providersLoading,
    openAddApi,
    refreshProviders,
    selectedProviderId,
    setSelectedProviderId,
    setScreenContext,
  } = useAppShell()
  const [deleting, setDeleting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => setScreenContext({ screen: 'apis' }), [setScreenContext])

  const handleDelete = async (providerId: string, name: string, endpointCount: number) => {
    const confirmed = window.confirm(
      `Delete ${name} and its ${endpointCount} ingested endpoints? This cannot be undone.`,
    )
    if (!confirmed) return
    setDeleting(providerId)
    setError(null)
    try {
      await deleteProvider(providerId)
      if (selectedProviderId === providerId) setSelectedProviderId(null)
      await refreshProviders()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Could not delete this API.')
    } finally {
      setDeleting(null)
    }
  }

  if (providersLoading) return <LoadingState label="Loading APIs…" />

  return (
    <section className="apis-screen">
      <div className="apis-screen-header">
        <div>
          <h1>APIs</h1>
          <p>Every API here uses the same ingestion, retrieval, agent, and verification pipeline.</p>
        </div>
        <button type="button" onClick={openAddApi}>Add API</button>
      </div>

      {error && <ErrorState message={error} />}
      {providers.length === 0 ? (
        <div className="apis-screen-empty">
          <h2>Connect your first API</h2>
          <p>Paste an OpenAPI URL or upload a JSON/YAML specification. No terminal required.</p>
          <button type="button" onClick={openAddApi}>Add API</button>
        </div>
      ) : (
        <ul className="apis-screen-list">
          {providers.map((provider) => (
            <li key={provider.id} className="apis-screen-card">
              <div className="apis-screen-card-main">
                <div>
                  <h2>{provider.name}</h2>
                  <code>{provider.id}</code>
                </div>
                <span data-ingested={provider.ingested}>{provider.ingested ? 'Ready' : 'Not ingested'}</span>
              </div>
              <dl>
                <div><dt>Endpoints</dt><dd>{provider.endpoint_count}</dd></div>
                <div><dt>Source</dt><dd>{provider.source.type} · {provider.source.location}</dd></div>
                <div><dt>Added</dt><dd>{provider.origin === 'runtime' ? 'In the app' : 'Project configuration'}</dd></div>
                <div><dt>Ingested</dt><dd>{formatDate(provider.ingested_at)}</dd></div>
              </dl>
              {!provider.evaluation_questions_defined && (
                <p className="apis-screen-eval-note">
                  No evaluation questions defined for this provider. Create <code>{provider.evaluation_questions_path}</code> to measure it.
                </p>
              )}
              <div className="apis-screen-card-actions">
                <button
                  type="button"
                  className="apis-screen-delete"
                  disabled={deleting === provider.id}
                  onClick={() => void handleDelete(provider.id, provider.name, provider.endpoint_count)}
                >
                  {deleting === provider.id ? 'Deleting…' : 'Delete'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
