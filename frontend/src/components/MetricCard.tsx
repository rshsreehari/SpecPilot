import './MetricCard.css'

export type MetricStatus = 'verified' | 'info' | 'warning' | 'error' | 'thinking'

export interface MetricCardProps {
  label: string
  value: string | number
  unit?: string
  status?: MetricStatus
  sampleSize?: number
}

const STATUS_LABEL: Record<MetricStatus, string> = {
  verified: 'Verified',
  info: 'Informational',
  warning: 'Warning',
  error: 'Error',
  thinking: 'In progress',
}

/** Apple Health style metric: one large numeral, one small label beneath. The dot
 * carries meaning via both color and an sr-only word, never color alone (WCAG). */
export function MetricCard({ label, value, unit, status, sampleSize }: MetricCardProps) {
  return (
    <div className="metric-card">
      {status && (
        <span className={`metric-card-dot metric-card-dot-${status}`} aria-hidden="true" />
      )}
      <div className="metric-card-value">
        {value}
        {unit && <span className="metric-card-unit">{unit}</span>}
      </div>
      <div className="metric-card-label">
        {label}
        {status && <span className="sr-only"> ({STATUS_LABEL[status]})</span>}
      </div>
      {sampleSize !== undefined && <div className="metric-card-sample">n={sampleSize}</div>}
    </div>
  )
}
