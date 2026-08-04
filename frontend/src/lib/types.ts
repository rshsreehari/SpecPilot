export type Strategy = 'naive' | 'bm25' | 'hybrid' | 'reranked'

export const STRATEGIES: Strategy[] = ['naive', 'bm25', 'hybrid', 'reranked']

export interface Citation {
  method: string
  path: string
  operation_id: string | null
  provider_id: string | null
  verified: boolean
}

export interface QueryResponse {
  answer: string
  code_snippet: string | null
  citations: Citation[]
  retrieved_chunk_ids: number[]
}

export interface Provider {
  id: string
  name: string
  ingested: boolean
  endpoint_count: number
  openapi_version: string | null
  ingested_at: string | null
  source: {
    type: 'url' | 'upload' | 'file'
    location: string
  }
  origin: 'bundled' | 'runtime'
  evaluation_questions_defined: boolean
  evaluation_questions_path: string
}

export type ProviderSourceType = 'url' | 'upload'

export interface ProviderSourceInput {
  source_type: ProviderSourceType
  url?: string
  spec_content?: string
}

export interface ProviderPreview {
  openapi_version: string
  title: string
  endpoint_count: number
  sample_paths: string[]
  detected_tags: string[]
  path_prefixes: Array<{ prefix: string; endpoint_count: number }>
  warnings: string[]
}

export interface ProviderCreateInput extends ProviderSourceInput {
  id: string
  name: string
  path_prefixes: string[]
}

export interface ProviderJob {
  job_id: string
  provider_id: string
  status: 'pending' | 'downloading' | 'parsing' | 'embedding' | 'done' | 'failed'
  progress: { current: number; total: number; stage_label: string }
  endpoint_count: number | null
  skipped: Array<{ kind: string; count: number; reason: string }>
  warnings: string[]
  error: string | null
}

export interface ProviderDeleteResult {
  provider_id: string
  deleted: {
    providers: number
    endpoints: number
    parameters: number
    chunks: number
    managed_spec_file: boolean
  }
}

export type AssistantMode = 'quick' | 'agent'

export interface ConversationTurn {
  id: string
  question: string
  mode: AssistantMode
  status: 'working' | 'done' | 'failed'
  answer: QueryResponse | null
  trace: TraceStep[]
  error: string | null
}

export interface TraceStep {
  step: number
  tool: string
  args: Record<string, unknown>
  result_summary: string
  duration_ms: number
  endpoint_ids: number[]
}

export interface AgentQueryResponse extends QueryResponse {
  trace: TraceStep[]
}

export interface EndpointSummary {
  id: number
  provider_id: string
  method: string
  path: string
  operation_id: string | null
  summary: string | null
}

export interface ParameterInfo {
  name: string
  location: string
  type: string | null
  required: boolean
  description: string | null
}

export interface EndpointDetail extends EndpointSummary {
  description: string | null
  parameters: ParameterInfo[]
}

export interface ReportSummary {
  id: string
  kind: 'eval' | 'comparison' | 'agent'
  model: string | null
  timestamp: string | null
  providers: string[]
  splits: string[]
}

/** Dynamic metric bag - keys are metric names (endpoint_accuracy, etc.) plus their
 * "_n" sample-size counterparts, values are numbers or null when a metric has no data
 * for that mode/split (e.g. recall_at_k for a no-retrieval baseline). */
export type MetricBag = Record<string, number | null> & { n: number }

export interface EndpointRef {
  method: string | null
  path: string
}

export interface QuestionRecord {
  question_id: string
  split: string
  category: string
  mode: string
  question: string
  answer: string
  code_snippet: string | null
  citations: Citation[]
  graded_endpoints: EndpointRef[]
  expected_endpoints: EndpointRef[]
  expected_endpoints_covered?: number
  trace?: TraceStep[]
  refused?: boolean
  tool_call_count?: number
  wasted_tool_call_count?: number
  latency_ms: number
}

export interface EvalReport {
  timestamp: string
  model: string
  provider?: string
  strategy?: string
  splits: Record<string, Record<string, MetricBag>>
  /** Absent on --all-providers reports (those have no single flat question list - see
   * per_provider below, each of which has its own). */
  questions?: QuestionRecord[]
  /** Present only on --all-providers reports: the pooled "splits" above is the combined
   * table across every provider; per_provider keeps each provider's own report alongside
   * it so the breakdown is never hidden behind the pooled number. */
  providers?: string[]
  per_provider?: Record<string, EvalReport>
}

// --- SSE event shapes, matching src/agent/loop.py's AgentEvent union ---

export interface ToolStartEvent {
  type: 'tool_start'
  step: number
  tool: string
  args: Record<string, unknown>
}

export interface ToolEndEvent {
  type: 'tool_end'
  step: number
  tool: string
  duration_ms: number
  summary: string
}

export interface TokenEvent {
  type: 'token'
  text: string
}

export interface DoneEvent {
  type: 'done'
  answer: QueryResponse
  trace: TraceStep[]
  prompt_tokens: number
  completion_tokens: number
}

export interface ErrorEvent {
  type: 'error'
  message: string
}

export type AgentSSEEvent = ToolStartEvent | ToolEndEvent | TokenEvent | DoneEvent | ErrorEvent

export interface ScreenContext {
  screen: 'ask' | 'endpoint_detail' | 'evaluation' | 'endpoints' | 'apis'
  method?: string
  path?: string
  strategy?: Strategy
  /** undefined/omitted means "search every ingested provider" - matches the backend's
   * provider_id=None convention (see src/retrieval/factory.py). */
  providerId?: string
}
