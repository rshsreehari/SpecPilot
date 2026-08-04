import { useCallback } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Moon, Plus, Sun } from 'lucide-react'
import { useTheme } from '../lib/useTheme'
import { useAppShell } from '../context/useAppShell'
import { SidePanel } from './SidePanel'
import { ProviderSelector } from './ProviderSelector'
import { AddApiModal } from './add-api/AddApiModal'
import './Layout.css'

const NAV_ITEMS = [
  { to: '/', label: 'Ask', end: true },
  { to: '/evaluation', label: 'Evaluation', end: false },
  { to: '/endpoints', label: 'Endpoints', end: false },
  { to: '/apis', label: 'APIs', end: false },
]

export function Layout() {
  const { theme, toggleTheme } = useTheme()
  const {
    refreshProviders,
    setSelectedProviderId,
    addApiOpen,
    openAddApi,
    closeAddApi,
  } = useAppShell()

  const handleProviderAdded = useCallback(async (providerId: string) => {
    await refreshProviders()
    setSelectedProviderId(providerId)
  }, [refreshProviders, setSelectedProviderId])

  return (
    <div className="layout">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <header className="layout-nav">
        <span className="layout-brand">SpecPilot</span>
        <nav aria-label="Main">
          <ul className="layout-nav-list">
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end} className="layout-nav-link">{item.label}</NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="layout-nav-actions">
          <ProviderSelector />
          <button type="button" onClick={openAddApi} className="layout-add-api">
            <Plus size={16} /> <span>Add API</span>
          </button>
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            className="layout-icon-button"
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      <div className="layout-body">
        <main id="main-content" className="layout-main" tabIndex={-1}><Outlet /></main>
        <SidePanel />
      </div>

      {addApiOpen && <AddApiModal onClose={closeAddApi} onComplete={handleProviderAdded} />}
    </div>
  )
}
