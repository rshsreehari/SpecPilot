import { useAppShell } from '../context/useAppShell'
import './ProviderSelector.css'

/** Global, app-wide selection (unlike the strategy selector, which is local to the Ask
 * screen's form) - the provider in scope here also filters the Endpoints screen, scopes
 * the Evaluation screen's default tab, and travels with every side-panel question. */
export function ProviderSelector() {
  const { providers, providersLoading, selectedProviderId, setSelectedProviderId } = useAppShell()

  if (providersLoading || providers.every((provider) => !provider.ingested)) return null

  return (
    <div className="provider-selector">
      <label htmlFor="provider-selector-select" className="sr-only">
        Provider
      </label>
      <select
        id="provider-selector-select"
        value={selectedProviderId ?? ''}
        onChange={(event) => setSelectedProviderId(event.target.value || null)}
      >
        <option value="">All providers</option>
        {providers.filter((provider) => provider.ingested).map((provider) => (
          <option key={provider.id} value={provider.id}>
            {provider.name}
          </option>
        ))}
      </select>
    </div>
  )
}
