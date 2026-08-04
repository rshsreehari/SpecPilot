import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { listEndpoints } from '../lib/api'
import { LoadingState, ErrorState, EmptyState } from '../components/DataStates'
import { useAppShell } from '../context/useAppShell'
import './EndpointsScreen.css'

export function EndpointsScreen() {
  const [searchParams] = useSearchParams()
  const [query, setQuery] = useState(searchParams.get('q') ?? '')
  const [debounced, setDebounced] = useState(query)
  const { setScreenContext, providers, selectedProviderId } = useAppShell()
  const [providerFilter, setProviderFilter] = useState(
    searchParams.get('provider_id') ?? selectedProviderId ?? '',
  )
  const showProviderColumn = providers.length > 1 && !providerFilter

  useEffect(() => {
    setScreenContext({ screen: 'endpoints', providerId: providerFilter || undefined })
  }, [setScreenContext, providerFilter])

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 250)
    return () => window.clearTimeout(timer)
  }, [query])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['endpoints', debounced, providerFilter],
    queryFn: () => listEndpoints(debounced || undefined, providerFilter || undefined),
  })

  return (
    <section className="endpoints-screen">
      <h1 className="endpoints-screen-title">Endpoints</h1>

      <div className="endpoints-screen-controls">
        <label htmlFor="endpoints-search" className="sr-only">
          Search endpoints
        </label>
        <input
          id="endpoints-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by path, summary, or operation ID…"
          className="endpoints-screen-search"
        />

        {providers.length > 1 && (
          <>
            <label htmlFor="endpoints-provider" className="sr-only">
              Provider
            </label>
            <select
              id="endpoints-provider"
              value={providerFilter}
              onChange={(event) => setProviderFilter(event.target.value)}
            >
              <option value="">All providers</option>
              {providers
                .filter((p) => p.ingested)
                .map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
            </select>
          </>
        )}
      </div>

      <div aria-live="polite">
        {isLoading && <LoadingState label="Loading endpoints…" />}
        {isError && <ErrorState message={error instanceof Error ? error.message : 'Failed to load endpoints.'} />}
        {!isLoading && !isError && data?.length === 0 && (
          <EmptyState message="No endpoints match that search." />
        )}
        {!isLoading && !isError && data && data.length > 0 && (
          <ul className="endpoints-screen-list">
            {data.map((endpoint) => (
              <li key={endpoint.id}>
                <Link to={`/endpoints/${endpoint.id}`} className="endpoints-screen-row">
                  <span className="endpoints-screen-method">{endpoint.method}</span>
                  <span className="endpoints-screen-path">{endpoint.path}</span>
                  {showProviderColumn && (
                    <span className="endpoints-screen-provider">{endpoint.provider_id}</span>
                  )}
                  {endpoint.summary && <span className="endpoints-screen-summary">{endpoint.summary}</span>}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
