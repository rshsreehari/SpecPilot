import type {
  AgentQueryResponse,
  EndpointDetail,
  EndpointSummary,
  EvalReport,
  Provider,
  ProviderCreateInput,
  ProviderDeleteResult,
  ProviderJob,
  ProviderPreview,
  ProviderSourceInput,
  QueryResponse,
  ReportSummary,
  Strategy,
} from './types'

class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    const body = await response.text()
    let message = body || response.statusText
    try {
      const parsed = JSON.parse(body) as { detail?: string | Array<{ msg?: string }> }
      if (typeof parsed.detail === 'string') message = parsed.detail
      if (Array.isArray(parsed.detail)) {
        message = parsed.detail.map((item) => item.msg).filter(Boolean).join(' ') || message
      }
    } catch {
      // Non-JSON error bodies are already readable as-is.
    }
    throw new ApiError(response.status, message)
  }
  return (await response.json()) as T
}

export function postQuery(
  question: string,
  strategy: Strategy,
  providerId?: string,
  topK = 5,
): Promise<QueryResponse> {
  return request<QueryResponse>('/query', {
    method: 'POST',
    body: JSON.stringify({ question, strategy, top_k: topK, provider_id: providerId ?? null }),
  })
}

export function postAgentQuery(
  question: string,
  strategy: Strategy,
  providerId?: string,
  topK = 5,
): Promise<AgentQueryResponse> {
  return request<AgentQueryResponse>('/agent/query', {
    method: 'POST',
    body: JSON.stringify({ question, strategy, top_k: topK, provider_id: providerId ?? null }),
  })
}

export function listProviders(): Promise<Provider[]> {
  return request<Provider[]>('/api/providers')
}

export function previewProvider(source: ProviderSourceInput): Promise<ProviderPreview> {
  return request<ProviderPreview>('/api/providers/preview', {
    method: 'POST',
    body: JSON.stringify(source),
  })
}

export function createProvider(input: ProviderCreateInput): Promise<{ job_id: string; provider_id: string }> {
  return request<{ job_id: string; provider_id: string }>('/api/providers', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function getProviderJob(jobId: string): Promise<ProviderJob> {
  return request<ProviderJob>(`/api/providers/jobs/${encodeURIComponent(jobId)}`)
}

export function deleteProvider(providerId: string): Promise<ProviderDeleteResult> {
  return request<ProviderDeleteResult>(`/api/providers/${encodeURIComponent(providerId)}`, {
    method: 'DELETE',
  })
}

export function listEndpoints(query?: string, providerId?: string): Promise<EndpointSummary[]> {
  const params = new URLSearchParams()
  if (query) params.set('q', query)
  if (providerId) params.set('provider_id', providerId)
  const qs = params.toString()
  return request<EndpointSummary[]>(`/api/endpoints${qs ? `?${qs}` : ''}`)
}

export function getEndpoint(id: number): Promise<EndpointDetail> {
  return request<EndpointDetail>(`/api/endpoints/${id}`)
}

export function listReports(providerId?: string): Promise<ReportSummary[]> {
  const params = providerId ? `?provider_id=${encodeURIComponent(providerId)}` : ''
  return request<ReportSummary[]>(`/api/reports${params}`)
}

export function getReport(id: string): Promise<EvalReport> {
  return request<EvalReport>(`/api/reports/${id}`)
}

export { ApiError }
