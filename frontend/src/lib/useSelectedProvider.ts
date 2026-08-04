import { useCallback, useState } from 'react'

const STORAGE_KEY = 'specpilot-provider'

/** null means "All providers" - matches the backend's provider_id=None convention
 * (search/verify across every ingested provider). Persists across reloads like theme
 * and side-panel state. */
export function useSelectedProvider(): {
  selectedProviderId: string | null
  setSelectedProviderId: (id: string | null) => void
} {
  const [selectedProviderId, setSelectedProviderIdState] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_KEY),
  )

  const setSelectedProviderId = useCallback((id: string | null) => {
    setSelectedProviderIdState(id)
    if (id) {
      localStorage.setItem(STORAGE_KEY, id)
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [])

  return { selectedProviderId, setSelectedProviderId }
}
