import { useEffect, useState } from 'react'
import { getProviderJob } from '../../lib/api'
import type { ProviderJob } from '../../lib/types'

interface ApiIngestStepProps {
  jobId: string
  onDone: (providerId: string) => void
  onBack: () => void
}

export function ApiIngestStep({ jobId, onDone, onBack }: ApiIngestStepProps) {
  const [job, setJob] = useState<ProviderJob | null>(null)
  const [pollError, setPollError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    let timer: number | undefined
    const poll = async () => {
      try {
        const next = await getProviderJob(jobId)
        if (!active) return
        setJob(next)
        if (next.status === 'done') {
          timer = window.setTimeout(() => onDone(next.provider_id), 700)
          return
        }
        if (next.status !== 'failed') timer = window.setTimeout(poll, 500)
      } catch (error) {
        if (active) setPollError(error instanceof Error ? error.message : 'Could not read job status.')
      }
    }
    void poll()
    return () => {
      active = false
      if (timer) window.clearTimeout(timer)
    }
  }, [jobId, onDone])

  const total = job?.progress.total ?? 0
  const percent = total > 0 ? Math.round(((job?.progress.current ?? 0) / total) * 100) : 8
  const failedMessage = job?.error ?? pollError

  return (
    <div className="add-api-ingesting" aria-live="polite">
      <h3>{job?.status === 'done' ? 'API ready' : job?.progress.stage_label ?? 'Starting ingestion…'}</h3>
      {!failedMessage && (
        <>
          <div className="add-api-progress" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${percent}%` }} />
          </div>
          <p>{job?.status === 'done' ? `${job.endpoint_count ?? 0} endpoints are ready to query.` : `${percent}% complete`}</p>
        </>
      )}
      {job?.skipped && job.skipped.length > 0 && (
        <ul>{job.skipped.map((item) => <li key={item.kind}>{item.count} skipped: {item.reason}</li>)}</ul>
      )}
      {failedMessage && (
        <>
          <p className="add-api-error" role="alert">{failedMessage}</p>
          <button type="button" className="add-api-secondary" onClick={onBack}>Back and fix input</button>
        </>
      )}
    </div>
  )
}
