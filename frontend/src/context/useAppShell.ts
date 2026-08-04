import { useContext } from 'react'
import { AppShellContext, type AppShellValue } from './appShellContextValue'

export function useAppShell(): AppShellValue {
  const context = useContext(AppShellContext)
  if (!context) throw new Error('useAppShell must be used within AppShellProvider')
  return context
}
