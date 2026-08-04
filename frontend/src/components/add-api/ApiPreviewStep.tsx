import type { ProviderPreview } from '../../lib/types'

interface ApiPreviewStepProps {
  preview: ProviderPreview
  providerId: string
  name: string
  selectedPrefixes: string[]
  setProviderId: (id: string) => void
  setName: (name: string) => void
  setSelectedPrefixes: (prefixes: string[]) => void
  error: string | null
  isLoading: boolean
  onBack: () => void
  onIngest: () => void
}

export function ApiPreviewStep(props: ApiPreviewStepProps) {
  const selectedCount = props.preview.path_prefixes
    .filter((item) => props.selectedPrefixes.includes(item.prefix))
    .reduce((total, item) => total + item.endpoint_count, 0)

  const togglePrefix = (prefix: string) => {
    props.setSelectedPrefixes(
      props.selectedPrefixes.includes(prefix)
        ? props.selectedPrefixes.filter((value) => value !== prefix)
        : [...props.selectedPrefixes, prefix],
    )
  }

  return (
    <>
      <div className="add-api-preview-summary">
        <div>
          <strong>{props.preview.title}</strong>
          <span>OpenAPI {props.preview.openapi_version}</span>
        </div>
        <strong>{props.preview.endpoint_count} endpoints</strong>
      </div>

      <div className="add-api-preview-paths">
        <h3>Sample paths</h3>
        <ul>
          {props.preview.sample_paths.slice(0, 5).map((path) => <li key={path}>{path}</li>)}
        </ul>
      </div>

      <div className="add-api-config-grid">
        <label htmlFor="add-api-id">Provider ID</label>
        <input
          id="add-api-id"
          value={props.providerId}
          onChange={(event) => props.setProviderId(event.target.value.toLowerCase())}
          aria-describedby="add-api-id-hint"
        />
        <p id="add-api-id-hint">2–40 lowercase letters, numbers, and hyphens.</p>

        <label htmlFor="add-api-name">Display name</label>
        <input id="add-api-name" value={props.name} onChange={(event) => props.setName(event.target.value)} />
      </div>

      {props.preview.path_prefixes.length > 0 && (
        <div className="add-api-prefixes">
          <h3>Include path groups</h3>
          <div>
            {props.preview.path_prefixes.map((item) => (
              <button
                key={item.prefix}
                type="button"
                aria-pressed={props.selectedPrefixes.includes(item.prefix)}
                data-selected={props.selectedPrefixes.includes(item.prefix)}
                onClick={() => togglePrefix(item.prefix)}
              >
                {props.selectedPrefixes.includes(item.prefix) ? '✓ ' : ''}
                {item.prefix} · {item.endpoint_count}
              </button>
            ))}
          </div>
          <p>Will ingest {selectedCount} of {props.preview.endpoint_count} endpoints.</p>
          {props.preview.endpoint_count > 300 && (
            <p>Filtering a large spec makes ingestion and evaluation iteration faster.</p>
          )}
        </div>
      )}

      {props.preview.warnings.length > 0 && (
        <div className="add-api-warnings">
          <h3>Warnings</h3>
          <ul>{props.preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </div>
      )}

      {props.error && <p className="add-api-error" role="alert">{props.error}</p>}
      <div className="add-api-actions">
        <button type="button" className="add-api-secondary" onClick={props.onBack}>Back</button>
        <button
          type="button"
          disabled={!props.providerId || !props.name.trim() || selectedCount === 0 || props.isLoading}
          onClick={props.onIngest}
        >
          {props.isLoading ? 'Starting…' : 'Ingest API'}
        </button>
      </div>
    </>
  )
}
