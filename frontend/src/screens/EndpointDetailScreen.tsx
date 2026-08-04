import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { getEndpoint } from '../lib/api'
import { LoadingState, ErrorState, EmptyState } from '../components/DataStates'
import { useAppShell } from '../context/useAppShell'
import './EndpointDetailScreen.css'

export function EndpointDetailScreen() {
  const { endpointId } = useParams<{ endpointId: string }>()
  const id = Number(endpointId)
  const { setScreenContext, askInPanel, screenContext, providers } = useAppShell()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['endpoint', id],
    queryFn: () => getEndpoint(id),
    enabled: Number.isFinite(id),
  })

  useEffect(() => {
    if (!data) return
    setScreenContext({
      screen: 'endpoint_detail',
      method: data.method,
      path: data.path,
      providerId: data.provider_id,
    })
  }, [data, setScreenContext])

  if (!Number.isFinite(id)) return <ErrorState message="Invalid endpoint ID." />
  if (isLoading) return <LoadingState label="Loading endpoint…" />
  if (isError) return <ErrorState message={error instanceof Error ? error.message : 'Endpoint not found.'} />
  if (!data) return <EmptyState message="No data for this endpoint." />

  return (
    <section className="endpoint-detail">
      <div className="endpoint-detail-header">
        <div>
          <span className="endpoint-detail-method">{data.method}</span>
          <span className="endpoint-detail-path">{data.path}</span>
          {providers.length > 1 && (
            <span className="endpoint-detail-provider">{data.provider_id}</span>
          )}
        </div>
        <button
          type="button"
          className="endpoint-detail-ask"
          onClick={() => askInPanel(`Explain how to use ${data.method} ${data.path}.`, screenContext.strategy ?? 'hybrid')}
        >
          Ask about this endpoint
        </button>
      </div>

      {data.summary && <p className="endpoint-detail-summary">{data.summary}</p>}
      {data.description && <p className="endpoint-detail-description">{data.description}</p>}

      <h2 className="endpoint-detail-section-title">Parameters</h2>
      {data.parameters.length === 0 ? (
        <EmptyState message="This endpoint takes no parameters." />
      ) : (
        <table className="endpoint-detail-table">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Location</th>
              <th scope="col">Type</th>
              <th scope="col">Required</th>
              <th scope="col">Description</th>
            </tr>
          </thead>
          <tbody>
            {data.parameters.map((param) => (
              <tr key={`${param.location}-${param.name}`}>
                <td className="endpoint-detail-mono">{param.name}</td>
                <td>{param.location}</td>
                <td className="endpoint-detail-mono">{param.type ?? '—'}</td>
                <td>{param.required ? 'Yes' : 'No'}</td>
                <td>{param.description ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
