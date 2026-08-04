import { Check, Loader2 } from 'lucide-react'
import type { ToolCardState } from '../lib/useAgentStream'
import './ToolCard.css'

const TOOL_LABEL: Record<string, string> = {
  search_docs: 'Searching docs',
  get_endpoint: 'Looking up endpoint',
  list_parameters: 'Listing parameters',
  find_related: 'Finding related endpoints',
}

function summarizeArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args)
  if (entries.length === 0) return ''
  return entries.map(([key, value]) => `${key}: ${JSON.stringify(value)}`).join(', ')
}

export function ToolCard({ card }: { card: ToolCardState }) {
  const label = TOOL_LABEL[card.tool] ?? card.tool
  const argsSummary = summarizeArgs(card.args)

  return (
    <li className="tool-card" data-status={card.status}>
      <span className="tool-card-icon" aria-hidden="true">
        {card.status === 'running' ? (
          <Loader2 className="tool-card-spinner" size={14} />
        ) : (
          <Check size={14} />
        )}
      </span>
      <div className="tool-card-body">
        <div className="tool-card-title">
          {label}
          {card.status === 'running' && <span className="sr-only"> (in progress)</span>}
        </div>
        {argsSummary && <div className="tool-card-args">{argsSummary}</div>}
        {card.summary && <div className="tool-card-summary">{card.summary}</div>}
      </div>
      {card.durationMs !== null && <span className="tool-card-duration">{card.durationMs}ms</span>}
    </li>
  )
}
