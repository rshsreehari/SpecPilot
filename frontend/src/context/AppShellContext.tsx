import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listProviders } from '../lib/api'
import { useConversation } from '../lib/useConversation'
import { useSidePanel } from '../lib/useSidePanel'
import { useSelectedProvider } from '../lib/useSelectedProvider'
import type { AssistantMode, Provider, ScreenContext, Strategy } from '../lib/types'
import { AppShellContext, type AppShellValue } from './appShellContextValue'

const DEFAULT_SCREEN_CONTEXT: ScreenContext = { screen: 'ask' }
const EMPTY_PROVIDERS: Provider[] = []

/** Single source of truth for the side panel, the ingested-provider list, and which
 * provider is currently selected - all shared across the Ask/Evaluation/Endpoint
 * screens. Screens call setScreenContext on mount/selection so the panel can resolve
 * pronouns like "this endpoint" against whatever the user is currently looking at, and
 * now against whichever provider that endpoint belongs to. */
export function AppShellProvider({ children }: { children: ReactNode }) {
  const panel = useSidePanel()
  const conversation = useConversation()
  const queryClient = useQueryClient()
  const [screenContext, setScreenContext] = useState<ScreenContext>(DEFAULT_SCREEN_CONTEXT)
  const { selectedProviderId, setSelectedProviderId } = useSelectedProvider()
  const [assistantMode, setAssistantMode] = useState<AssistantMode>('quick')
  const [assistantDraft, setAssistantDraft] = useState('')
  const [addApiOpen, setAddApiOpen] = useState(false)

  const providersQuery = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const providers = providersQuery.data ?? EMPTY_PROVIDERS

  useEffect(() => {
    if (selectedProviderId && !providers.some((provider) => provider.id === selectedProviderId)) {
      setSelectedProviderId(null)
    }
  }, [providers, selectedProviderId, setSelectedProviderId])

  const value = useMemo<AppShellValue>(
    () => ({
      panel,
      conversation,
      screenContext,
      setScreenContext,
      askInPanel: (question: string, strategy: Strategy) => {
        panel.open()
        // The active screen's own provider (e.g. the endpoint detail screen's endpoint)
        // takes priority over the global selector - asking "about this endpoint" must
        // stay scoped to that endpoint's provider even if the header selector is set to
        // a different provider or "All providers".
        const providerId = screenContext.providerId ?? selectedProviderId ?? undefined
        conversation.ask(question, assistantMode, strategy, {
          ...screenContext,
          strategy,
          providerId,
        })
      },
      providers,
      providersLoading: providersQuery.isLoading,
      selectedProviderId,
      setSelectedProviderId,
      assistantMode,
      setAssistantMode,
      assistantDraft,
      setAssistantDraft,
      addApiOpen,
      openAddApi: () => setAddApiOpen(true),
      closeAddApi: () => setAddApiOpen(false),
      refreshProviders: async () => {
        await queryClient.invalidateQueries({ queryKey: ['providers'] })
      },
    }),
    [
      panel,
      conversation,
      screenContext,
      providers,
      providersQuery.isLoading,
      selectedProviderId,
      setSelectedProviderId,
      assistantMode,
      assistantDraft,
      addApiOpen,
      queryClient,
    ],
  )

  return <AppShellContext.Provider value={value}>{children}</AppShellContext.Provider>
}
