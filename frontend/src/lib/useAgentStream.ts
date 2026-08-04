import { useCallback, useRef, useState } from 'react'
import type { DoneEvent, ErrorEvent, ScreenContext, ToolEndEvent, ToolStartEvent } from './types'

export interface ToolCardState {
  step: number
  tool: string
  args: Record<string, unknown>
  status: 'running' | 'done'
  durationMs: number | null
  summary: string | null
}

export interface AgentStreamState {
  isStreaming: boolean
  toolCards: ToolCardState[]
  answerText: string
  done: DoneEvent | null
  error: string | null
  ask: (question: string, context: ScreenContext) => void
  stop: () => void
  reset: () => void
}

function parseData<T>(event: Event): T | null {
  const data = (event as MessageEvent<string>).data
  if (!data) return null
  try {
    return JSON.parse(data) as T
  } catch {
    return null
  }
}

/** One EventSource per turn, closed on done/error/stop/unmount. The backend's "token"
 * event carries the complete final answer, not an incremental delta (see BUGS.md) - so
 * answerText is replaced, not appended. */
export function useAgentStream(): AgentStreamState {
  const [isStreaming, setIsStreaming] = useState(false)
  const [toolCards, setToolCards] = useState<ToolCardState[]>([])
  const [answerText, setAnswerText] = useState('')
  const [done, setDone] = useState<DoneEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const sourceRef = useRef<EventSource | null>(null)

  const stop = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
    setIsStreaming(false)
  }, [])

  const reset = useCallback(() => {
    stop()
    setToolCards([])
    setAnswerText('')
    setDone(null)
    setError(null)
  }, [stop])

  const ask = useCallback(
    (question: string, context: ScreenContext) => {
      stop()
      setToolCards([])
      setAnswerText('')
      setDone(null)
      setError(null)
      setIsStreaming(true)

      const sessionId = crypto.randomUUID()
      const params = new URLSearchParams({ question, screen: context.screen })
      if (context.strategy) params.set('strategy', context.strategy)
      if (context.providerId) params.set('provider_id', context.providerId)
      if (context.method) params.set('context_method', context.method)
      if (context.path) params.set('context_path', context.path)

      const source = new EventSource(`/agent/stream/${sessionId}?${params.toString()}`)
      sourceRef.current = source

      source.addEventListener('tool_start', (event) => {
        const data = parseData<ToolStartEvent>(event)
        if (!data) return
        setToolCards((cards) => [
          ...cards,
          { step: data.step, tool: data.tool, args: data.args, status: 'running', durationMs: null, summary: null },
        ])
      })

      source.addEventListener('tool_end', (event) => {
        const data = parseData<ToolEndEvent>(event)
        if (!data) return
        setToolCards((cards) =>
          cards.map((card) =>
            card.step === data.step
              ? { ...card, status: 'done', durationMs: data.duration_ms, summary: data.summary }
              : card,
          ),
        )
      })

      source.addEventListener('token', (event) => {
        const data = parseData<{ type: 'token'; text: string }>(event)
        if (data) setAnswerText(data.text)
      })

      source.addEventListener('done', (event) => {
        const data = parseData<DoneEvent>(event)
        if (data) setDone(data)
        setIsStreaming(false)
        source.close()
        sourceRef.current = null
      })

      // The server's named "error" SSE event and the browser's built-in EventSource
      // connection-error both dispatch through this same handler (a well-known SSE
      // quirk: "error" is a reserved event type) - parseData returning null covers the
      // connection-failure case, which never carries a data payload.
      source.addEventListener('error', (event) => {
        const data = parseData<ErrorEvent>(event)
        setError(data?.message ?? 'Connection to the agent was lost.')
        setIsStreaming(false)
        source.close()
        sourceRef.current = null
      })
    },
    [stop],
  )

  return { isStreaming, toolCards, answerText, done, error, ask, stop, reset }
}
