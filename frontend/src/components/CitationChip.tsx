import { Check, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Citation } from '../lib/types'
import './CitationChip.css'

export interface CitationChipProps {
  citation: Citation
  /** Show a small provider label on the chip. Only meaningful (and only passed as true)
   * when more than one provider is ingested - with a single provider it's just noise,
   * since every citation obviously belongs to it. */
  showProvider?: boolean
}

/** verified comes from the backend's mechanical check against the OpenAPI spec
 * (src/eval/truth.py::Truth.endpoint_exists) - never fabricated, never LLM-graded. */
export function CitationChip({ citation, showProvider = false }: CitationChipProps) {
  const label = `${citation.method} ${citation.path}`
  const params = new URLSearchParams({ q: citation.path })
  if (citation.provider_id) params.set('provider_id', citation.provider_id)

  return (
    <Link to={`/endpoints?${params.toString()}`} className="citation-chip" data-verified={citation.verified}>
      {citation.verified ? (
        <Check size={12} aria-hidden="true" />
      ) : (
        <X size={12} aria-hidden="true" />
      )}
      <span className="citation-chip-label">{label}</span>
      {showProvider && citation.provider_id && (
        <span className="citation-chip-provider">{citation.provider_id}</span>
      )}
      <span className="sr-only">{citation.verified ? ', verified against spec' : ', not found in spec'}</span>
    </Link>
  )
}
