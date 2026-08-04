import { useCallback, useEffect, useState } from 'react'

const WIDTH_KEY = 'specpilot-panel-width'
const OPEN_KEY = 'specpilot-panel-open'
const MIN_WIDTH = 320
const MAX_WIDTH = 560
const DEFAULT_WIDTH = 400

function clampWidth(width: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, width))
}

export interface SidePanelState {
  isOpen: boolean
  width: number
  toggle: () => void
  open: () => void
  close: () => void
  setWidth: (width: number) => void
}

/** Open/closed and width both persist across screens and reloads, per BUILD.md
 * Appendix B ("Persists across screens and remembers open/closed and width"). */
export function useSidePanel(): SidePanelState {
  const [isOpen, setIsOpen] = useState<boolean>(() => {
    const stored = localStorage.getItem(OPEN_KEY)
    return stored === null ? true : stored === 'true'
  })
  const [width, setWidthState] = useState<number>(() => {
    const stored = Number(localStorage.getItem(WIDTH_KEY))
    return stored ? clampWidth(stored) : DEFAULT_WIDTH
  })

  useEffect(() => {
    localStorage.setItem(OPEN_KEY, String(isOpen))
  }, [isOpen])

  const setWidth = useCallback((next: number) => {
    const clamped = clampWidth(next)
    setWidthState(clamped)
    localStorage.setItem(WIDTH_KEY, String(clamped))
  }, [])

  const toggle = useCallback(() => setIsOpen((v) => !v), [])
  const open = useCallback(() => setIsOpen(true), [])
  const close = useCallback(() => setIsOpen(false), [])

  return { isOpen, width, toggle, open, close, setWidth }
}
