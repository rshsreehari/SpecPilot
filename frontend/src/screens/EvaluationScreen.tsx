import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { getReport, listReports } from '../lib/api'
import { MetricCard } from '../components/MetricCard'
import { StrategyBarChart } from '../components/StrategyBarChart'
import { QuestionTable } from '../components/QuestionTable'
import { LoadingState, ErrorState, EmptyState } from '../components/DataStates'
import { METRIC_TABLE, formatMetric, pickPrimaryMode } from '../lib/formatMetric'
import { useAppShell } from '../context/useAppShell'
import type { EvalReport } from '../lib/types'
import './EvaluationScreen.css'

const HERO_METRICS = ['endpoint_accuracy', 'parameter_hallucination_rate', 'correct_refusal_rate', 'avg_cost_usd']

export function EvaluationScreen() {
  const { reportId } = useParams<{ reportId: string }>()
  const navigate = useNavigate()
  const { setScreenContext, selectedProviderId, providers } = useAppShell()
  const [split, setSplit] = useState<string>('')
  const [chartMetricKey, setChartMetricKey] = useState('endpoint_accuracy')
  const [providerTab, setProviderTab] = useState<string>('combined')

  useEffect(() => {
    setScreenContext({ screen: 'evaluation' })
  }, [setScreenContext])

  const reportsQuery = useQuery({
    queryKey: ['reports', selectedProviderId],
    queryFn: () => listReports(selectedProviderId ?? undefined),
  })
  const activeReportId = reportId ?? reportsQuery.data?.[0]?.id

  const reportQuery = useQuery({
    queryKey: ['report', activeReportId],
    queryFn: () => getReport(activeReportId as string),
    enabled: Boolean(activeReportId),
  })

  // An --all-providers report has no flat "questions" list of its own and a "splits"
  // table that's the pooled combination across every provider; per_provider keeps each
  // provider's own full report (including its own questions) alongside it. Reset the
  // tab back to "combined" whenever the report itself changes, so switching reports
  // never leaves the tab pointing at a provider the new report doesn't have.
  const isAllProviders = Boolean(reportQuery.data?.providers)
  useEffect(() => {
    setProviderTab('combined')
  }, [activeReportId])

  const activeReportData: EvalReport | undefined =
    isAllProviders && providerTab !== 'combined'
      ? reportQuery.data?.per_provider?.[providerTab]
      : reportQuery.data

  const splits = useMemo(
    () => (activeReportData ? Object.keys(activeReportData.splits) : []),
    [activeReportData],
  )
  const activeSplit = splits.includes(split) ? split : (splits.includes('holdout') ? 'holdout' : splits[0]) ?? ''
  const modes = activeSplit ? activeReportData?.splits[activeSplit] ?? {} : {}
  const primaryMode = pickPrimaryMode(Object.keys(modes))
  const heroBag = primaryMode ? modes[primaryMode] : undefined

  if (reportsQuery.isLoading) return <LoadingState label="Loading reports…" />
  if (reportsQuery.isError) {
    return <ErrorState message={reportsQuery.error instanceof Error ? reportsQuery.error.message : 'Failed to load reports.'} />
  }
  const selectedProvider = providers.find((provider) => provider.id === selectedProviderId)
  if (selectedProvider && !selectedProvider.evaluation_questions_defined) {
    return (
      <EmptyState
        message={`No evaluation questions defined for this provider. Create ${selectedProvider.evaluation_questions_path} to measure it.`}
      />
    )
  }
  if (reportsQuery.data && reportsQuery.data.length === 0) {
    return <EmptyState message="No eval reports yet. Run `specpilot eval` or `specpilot compare` to produce one." />
  }

  return (
    <section className="evaluation-screen">
      <div className="evaluation-screen-header">
        <h1 className="evaluation-screen-title">Evaluation</h1>
        <div className="evaluation-screen-controls">
          <label htmlFor="report-select" className="sr-only">
            Report
          </label>
          <select
            id="report-select"
            value={activeReportId ?? ''}
            onChange={(event) => navigate(`/evaluation/${event.target.value}`)}
          >
            {reportsQuery.data?.map((report) => (
              <option key={report.id} value={report.id}>
                {report.kind} · {report.providers.join('+') || '?'} · {report.timestamp ?? report.id}
              </option>
            ))}
          </select>

          {splits.length > 1 && (
            <>
              <label htmlFor="split-select" className="sr-only">
                Split
              </label>
              <select id="split-select" value={activeSplit} onChange={(event) => setSplit(event.target.value)}>
                {splits.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </>
          )}
        </div>
      </div>

      {isAllProviders && reportQuery.data?.providers && (
        <div className="evaluation-screen-provider-tabs" role="tablist" aria-label="Provider">
          <button
            type="button"
            role="tab"
            aria-selected={providerTab === 'combined'}
            className="evaluation-screen-tab"
            data-active={providerTab === 'combined'}
            onClick={() => setProviderTab('combined')}
          >
            Combined
          </button>
          {reportQuery.data.providers.map((providerId) => (
            <button
              key={providerId}
              type="button"
              role="tab"
              aria-selected={providerTab === providerId}
              className="evaluation-screen-tab"
              data-active={providerTab === providerId}
              onClick={() => setProviderTab(providerId)}
            >
              {providerId}
            </button>
          ))}
        </div>
      )}

      {reportQuery.isLoading && <LoadingState label="Loading report…" />}
      {reportQuery.isError && (
        <ErrorState message={reportQuery.error instanceof Error ? reportQuery.error.message : 'Failed to load report.'} />
      )}

      {activeReportData && (
        <>
          {providerTab === 'combined' && isAllProviders && (
            <p className="evaluation-screen-pooled-note">
              Pooled across every provider's questions - never a plain average of each
              provider's own percentages. See each provider's tab for its own numbers.
            </p>
          )}

          <div className="evaluation-screen-hero" aria-label={`Headline metrics for ${primaryMode ?? 'model'}`}>
            {HERO_METRICS.map((key) => {
              const meta = METRIC_TABLE.find((m) => m.key === key)
              if (!meta || !heroBag) return null
              const nKey = `${key}_n`
              return (
                <MetricCard
                  key={key}
                  label={meta.label}
                  value={formatMetric(heroBag[key], meta.kind)}
                  sampleSize={typeof heroBag[nKey] === 'number' ? heroBag[nKey] ?? undefined : undefined}
                />
              )
            })}
          </div>

          <div className="evaluation-screen-chart">
            <div className="evaluation-screen-chart-header">
              <h2>Mode comparison</h2>
              <label htmlFor="chart-metric" className="sr-only">
                Metric
              </label>
              <select id="chart-metric" value={chartMetricKey} onChange={(event) => setChartMetricKey(event.target.value)}>
                {METRIC_TABLE.map((meta) => (
                  <option key={meta.key} value={meta.key}>
                    {meta.label}
                  </option>
                ))}
              </select>
            </div>
            <StrategyBarChart
              modes={modes}
              // METRIC_TABLE is a fixed non-empty literal declared in lib/formatMetric.ts,
              // so the fallback index is always in range.
              metric={METRIC_TABLE.find((m) => m.key === chartMetricKey) ?? METRIC_TABLE[0]!}
            />
          </div>

          {activeReportData.questions ? (
            <>
              <h2 className="evaluation-screen-section-title">Per-question results ({activeSplit})</h2>
              <QuestionTable
                questions={activeReportData.questions.filter((q) => q.split === activeSplit)}
              />
            </>
          ) : (
            <EmptyState message="Per-question detail is available under each provider's tab above." />
          )}
        </>
      )}
    </section>
  )
}
