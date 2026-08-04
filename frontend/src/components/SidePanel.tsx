import { useEffect, useRef, useState, type FormEvent } from 'react'
import { MessageSquare, PanelRightClose, Square } from 'lucide-react'
import { useAppShell } from '../context/useAppShell'
import { usePanelResize } from '../lib/usePanelResize'
import type { Strategy } from '../lib/types'
import { ToolCard } from './ToolCard'
import './SidePanel.css'

const SCREEN_LABEL: Record<string, string> = {
  ask: 'Ask',
  evaluation: 'Evaluation',
  endpoints: 'Endpoints',
  endpoint_detail: 'this endpoint',
  apis: 'APIs',
}

const PANEL_EXAMPLES = [
  'Which fields are required to create this resource?',
  'Show me a complete request example.',
  'What related operations are needed for this workflow?',
]

export function SidePanel() {
  const {
    panel,
    conversation,
    screenContext,
    selectedProviderId,
    providers,
    assistantMode,
    setAssistantMode,
    assistantDraft,
    setAssistantDraft,
  } = useAppShell()
  const { startDragging } = usePanelResize(panel.setWidth)
  const [strategy, setStrategy] = useState<Strategy>('hybrid')
  const transcriptRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' })
  }, [conversation.turns, conversation.stream.toolCards])

  if (!panel.isOpen) {
    return (
      <button type="button" className="side-panel-tab" onClick={panel.open} aria-label="Open API assistant">
        <MessageSquare size={18} />
        <span>Ask</span>
      </button>
    )
  }

  const contextLabel = SCREEN_LABEL[screenContext.screen] ?? screenContext.screen
  const effectiveProviderId = screenContext.providerId ?? selectedProviderId ?? undefined
  const providerLabel = providers.find((provider) => provider.id === effectiveProviderId)?.name ?? 'all APIs'

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const question = assistantDraft.trim()
    if (!question || conversation.isWorking) return
    conversation.ask(question, assistantMode, strategy, {
      ...screenContext,
      strategy,
      providerId: effectiveProviderId,
    })
    setAssistantDraft('')
  }

  return (
    <aside className="side-panel" style={{ width: panel.width }} aria-label="API assistant">
      <button
        type="button"
        className="side-panel-resize-handle"
        aria-label="Resize assistant panel"
        onPointerDown={startDragging}
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft') panel.setWidth(panel.width + 16)
          if (event.key === 'ArrowRight') panel.setWidth(panel.width - 16)
        }}
      />
      <header className="side-panel-header">
        <div>
          <h2 className="side-panel-title">API Assistant</h2>
          <p>{contextLabel} · {providerLabel}</p>
        </div>
        <button type="button" className="side-panel-close" onClick={panel.close} aria-label="Collapse assistant">
          <PanelRightClose size={18} />
        </button>
      </header>

      <div className="side-panel-mode" role="group" aria-label="Answer mode">
        <button type="button" data-active={assistantMode === 'quick'} onClick={() => setAssistantMode('quick')}>Quick</button>
        <button type="button" data-active={assistantMode === 'agent'} onClick={() => setAssistantMode('agent')}>Agent</button>
      </div>
      <p className="side-panel-mode-help">
        {assistantMode === 'quick'
          ? 'Quick searches once for a focused answer.'
          : 'Agent chains several API lookups and shows its work.'}
      </p>

      <div ref={transcriptRef} className="side-panel-body" aria-live="polite">
        {conversation.turns.map((turn) => (
          <div key={turn.id} className="side-panel-turn">
            <p className="side-panel-question">{turn.question}</p>
            {turn.trace.length > 0 && (
              <ul className="side-panel-tools">
                {turn.trace.map((step) => (
                  <ToolCard
                    key={step.step}
                    card={{
                      step: step.step,
                      tool: step.tool,
                      args: step.args,
                      status: 'done',
                      durationMs: step.duration_ms,
                      summary: step.result_summary,
                    }}
                  />
                ))}
              </ul>
            )}
            {turn.answer && <p className="side-panel-response">{turn.answer.answer}</p>}
            {turn.status === 'working' && <p className="side-panel-status">Working…</p>}
            {turn.error && <p className="side-panel-error">{turn.error}</p>}
          </div>
        ))}

        {conversation.stream.toolCards.length > 0 && conversation.stream.isStreaming && (
          <ul className="side-panel-tools">
            {conversation.stream.toolCards.map((card) => <ToolCard key={card.step} card={card} />)}
          </ul>
        )}

        {conversation.turns.length === 0 && (
          <div className="side-panel-empty">
            <p><strong>Ask about exact endpoints, parameters, or complete workflows.</strong></p>
            <p>Quick handles one lookup. Agent connects multiple operations when the task has several steps.</p>
            <div>
              {PANEL_EXAMPLES.map((question) => (
                <button key={question} type="button" onClick={() => setAssistantDraft(question)}>{question}</button>
              ))}
            </div>
          </div>
        )}
      </div>

      <form className="side-panel-form" onSubmit={handleSubmit}>
        <label htmlFor="side-panel-input" className="sr-only">Ask the API assistant</label>
        <textarea
          id="side-panel-input"
          value={assistantDraft}
          onChange={(event) => setAssistantDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
          placeholder="Ask about this API…"
          rows={3}
          disabled={conversation.isWorking}
        />
        <div className="side-panel-composer-actions">
          <select value={strategy} onChange={(event) => setStrategy(event.target.value as Strategy)} aria-label="Retrieval strategy">
            <option value="naive">Naive</option>
            <option value="bm25">BM25</option>
            <option value="hybrid">Hybrid</option>
            <option value="reranked">Reranked</option>
          </select>
          {conversation.stream.isStreaming ? (
            <button type="button" className="side-panel-stop" onClick={conversation.stop} aria-label="Stop agent"><Square size={14} /></button>
          ) : (
            <button type="submit" disabled={!assistantDraft.trim() || conversation.isWorking}>{conversation.isWorking ? 'Working…' : 'Ask'}</button>
          )}
        </div>
      </form>
    </aside>
  )
}
