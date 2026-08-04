import { useCallback, useRef } from 'react'

/** Drag-to-resize on the panel's left edge. Width grows as the pointer moves left
 * (the panel is anchored to the right edge of the viewport). */
export function usePanelResize(setWidth: (width: number) => void) {
  const draggingRef = useRef(false)

  const onPointerMove = useCallback(
    (event: PointerEvent) => {
      if (!draggingRef.current) return
      setWidth(window.innerWidth - event.clientX)
    },
    [setWidth],
  )

  const stopDragging = useCallback(() => {
    draggingRef.current = false
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', stopDragging)
  }, [onPointerMove])

  const startDragging = useCallback(() => {
    draggingRef.current = true
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', stopDragging)
  }, [onPointerMove, stopDragging])

  return { startDragging }
}
