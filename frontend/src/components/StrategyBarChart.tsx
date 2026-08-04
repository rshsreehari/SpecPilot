import type { MetricBag } from '../lib/types'
import { formatMetric, type MetricMeta } from '../lib/formatMetric'
import './StrategyBarChart.css'

export interface StrategyBarChartProps {
  modes: Record<string, MetricBag>
  metric: MetricMeta
}

/** Plain CSS bars, not a charting library - the project avoids third-party UI/chart
 * dependencies (CLAUDE.md: plain CSS with design tokens only). */
export function StrategyBarChart({ modes, metric }: StrategyBarChartProps) {
  const entries = Object.entries(modes)
  const values = entries.map(([, bag]) => bag[metric.key] ?? 0)
  const max = Math.max(...values, 0.0001)

  return (
    // Not role="img": the mode label and formatted value are real text, read directly
    // by assistive tech. Only the bar fill itself is decorative.
    <div className="strategy-bar-chart" aria-label={`${metric.label} by mode`}>
      {entries.map(([mode, bag]) => {
        const value = bag[metric.key]
        const width = value === null || value === undefined ? 0 : (value / max) * 100
        return (
          <div className="strategy-bar-row" key={mode}>
            <span className="strategy-bar-label">{mode}</span>
            <div className="strategy-bar-track" aria-hidden="true">
              <div className="strategy-bar-fill" style={{ width: `${width}%` }} />
            </div>
            <span className="strategy-bar-value">{formatMetric(value, metric.kind)}</span>
          </div>
        )
      })}
    </div>
  )
}
