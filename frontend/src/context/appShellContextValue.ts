import { createContext } from 'react'
import type { ConversationState } from '../lib/useConversation'
import type { SidePanelState } from '../lib/useSidePanel'
import type { AssistantMode, Provider, ScreenContext, Strategy } from '../lib/types'

export interface AppShellValue {
  panel: SidePanelState
  conversation: ConversationState
  screenContext: ScreenContext
  setScreenContext: (context: ScreenContext) => void
  askInPanel: (question: string, strategy: Strategy) => void
  providers: Provider[]
  providersLoading: boolean
  selectedProviderId: string | null
  setSelectedProviderId: (id: string | null) => void
  assistantMode: AssistantMode
  setAssistantMode: (mode: AssistantMode) => void
  assistantDraft: string
  setAssistantDraft: (draft: string) => void
  addApiOpen: boolean
  openAddApi: () => void
  closeAddApi: () => void
  refreshProviders: () => Promise<void>
}

export const AppShellContext = createContext<AppShellValue | null>(null)
