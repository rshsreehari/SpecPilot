import { useCallback, useEffect, useRef, useState } from 'react'
import { postQuery } from './api'
import { useAgentStream, type AgentStreamState } from './useAgentStream'
import type {
  AssistantMode,
  ConversationTurn,
  ScreenContext,
  Strategy,
} from './types'

function turnId(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
}

export interface ConversationState {
  turns: ConversationTurn[]
  isWorking: boolean
  stream: AgentStreamState
  ask: (
    question: string,
    mode: AssistantMode,
    strategy: Strategy,
    context: ScreenContext,
  ) => void
  stop: () => void
  clear: () => void
}

export function useConversation(): ConversationState {
  const stream = useAgentStream()
  const [turns, setTurns] = useState<ConversationTurn[]>([])
  const [quickWorking, setQuickWorking] = useState(false)
  const pendingAgentId = useRef<string | null>(null)

  useEffect(() => {
    const id = pendingAgentId.current
    if (!id || !stream.done) return
    setTurns((current) =>
      current.map((turn) =>
        turn.id === id
          ? {
              ...turn,
              status: 'done',
              answer: stream.done?.answer ?? null,
              trace: stream.done?.trace ?? [],
            }
          : turn,
      ),
    )
    pendingAgentId.current = null
  }, [stream.done])

  useEffect(() => {
    const id = pendingAgentId.current
    if (!id || !stream.error) return
    setTurns((current) =>
      current.map((turn) =>
        turn.id === id ? { ...turn, status: 'failed', error: stream.error } : turn,
      ),
    )
    pendingAgentId.current = null
  }, [stream.error])

  const ask = useCallback(
    (question: string, mode: AssistantMode, strategy: Strategy, context: ScreenContext) => {
      if (quickWorking || stream.isStreaming) return
      const id = turnId()
      const pending: ConversationTurn = {
        id,
        question,
        mode,
        status: 'working',
        answer: null,
        trace: [],
        error: null,
      }
      setTurns((current) => [...current, pending])

      if (mode === 'agent') {
        pendingAgentId.current = id
        stream.ask(question, { ...context, strategy })
        return
      }

      setQuickWorking(true)
      void postQuery(question, strategy, context.providerId)
        .then((answer) => {
          setTurns((current) =>
            current.map((turn) =>
              turn.id === id ? { ...turn, status: 'done', answer } : turn,
            ),
          )
        })
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : 'The request failed.'
          setTurns((current) =>
            current.map((turn) =>
              turn.id === id ? { ...turn, status: 'failed', error: message } : turn,
            ),
          )
        })
        .finally(() => setQuickWorking(false))
    },
    [quickWorking, stream],
  )

  const stop = useCallback(() => {
    const id = pendingAgentId.current
    stream.stop()
    if (id) {
      setTurns((current) =>
        current.map((turn) =>
          turn.id === id ? { ...turn, status: 'failed', error: 'Stopped by user.' } : turn,
        ),
      )
      pendingAgentId.current = null
    }
  }, [stream])

  const clear = useCallback(() => {
    stop()
    stream.reset()
    setTurns([])
  }, [stop, stream])

  return {
    turns,
    isWorking: quickWorking || stream.isStreaming,
    stream,
    ask,
    stop,
    clear,
  }
}
