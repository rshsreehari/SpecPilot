export type MetricKind = 'pct' | 'float' | 'ms' | 'num' | 'cost'

export interface MetricMeta {
  key: string
  label: string
  kind: MetricKind
}

/** Mirrors src/eval/report.py::_TABLE_METRICS - the report JSON's keys and formatting
 * are defined there; this is a display-only mirror, not a second source of truth. */
export const METRIC_TABLE: MetricMeta[] = [
  { key: 'endpoint_accuracy', label: 'Endpoint accuracy', kind: 'pct' },
  { key: 'parameter_hallucination_rate', label: 'Parameter hallucination', kind: 'pct' },
  { key: 'endpoint_recall', label: 'Endpoint recall', kind: 'pct' },
  { key: 'recall_at_k', label: 'Recall@k', kind: 'pct' },
  { key: 'mrr', label: 'MRR', kind: 'float' },
  { key: 'correct_refusal_rate', label: 'Correct refusal rate', kind: 'pct' },
  { key: 'latency_p50_ms', label: 'Latency p50', kind: 'ms' },
  { key: 'latency_p95_ms', label: 'Latency p95', kind: 'ms' },
  { key: 'avg_prompt_tokens', label: 'Avg tokens in', kind: 'num' },
  { key: 'avg_completion_tokens', label: 'Avg tokens out', kind: 'num' },
  { key: 'avg_cost_usd', label: 'Cost per query', kind: 'cost' },
]

/** Baseline modes carry no retrieval signal - never the "hero"/primary mode a report
 * opens on. Matches src/observability.py::_BASELINE_MODES. */
export const BASELINE_MODES = new Set(['no_retrieval', 'single_pass'])

export function formatMetric(value: number | null | undefined, kind: MetricKind): string {
  if (value === null || value === undefined) return '–'
  switch (kind) {
    case 'pct':
      return `${Math.round(value * 100)}%`
    case 'float':
      return value.toFixed(2)
    case 'ms':
      return `${(value / 1000).toFixed(1)}s`
    case 'num':
      return value.toFixed(0)
    case 'cost':
      return `$${value.toFixed(4)}`
    default:
      return String(value)
  }
}

export function pickPrimaryMode(modes: string[]): string | undefined {
  const ranked = [...modes].sort((a, b) => Number(BASELINE_MODES.has(a)) - Number(BASELINE_MODES.has(b)))
  return ranked[0]
}
