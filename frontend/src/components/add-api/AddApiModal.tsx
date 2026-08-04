import { useCallback, useState } from 'react'
import { X } from 'lucide-react'
import { createProvider, previewProvider } from '../../lib/api'
import type { ProviderPreview, ProviderSourceType } from '../../lib/types'
import { ApiIngestStep } from './ApiIngestStep'
import { ApiPreviewStep } from './ApiPreviewStep'
import { ApiSourceStep } from './ApiSourceStep'
import { slugifyProviderId } from './slugifyProviderId'
import './AddApiModal.css'

interface AddApiModalProps {
  onClose: () => void
  onComplete: (providerId: string) => Promise<void>
}

export function AddApiModal({ onClose, onComplete }: AddApiModalProps) {
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [sourceType, setSourceType] = useState<ProviderSourceType>('url')
  const [url, setUrl] = useState('')
  const [specContent, setSpecContent] = useState('')
  const [fileName, setFileName] = useState('')
  const [preview, setPreview] = useState<ProviderPreview | null>(null)
  const [providerId, setProviderId] = useState('')
  const [name, setName] = useState('')
  const [selectedPrefixes, setSelectedPrefixes] = useState<string[]>([])
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const source = sourceType === 'url'
    ? { source_type: sourceType, url: url.trim() }
    : { source_type: sourceType, spec_content: specContent }

  const handlePreview = async () => {
    setError(null)
    setIsLoading(true)
    try {
      const result = await previewProvider(source)
      setPreview(result)
      setProviderId(slugifyProviderId(result.title) || 'my-api')
      setName(result.title)
      setSelectedPrefixes(result.path_prefixes.map((item) => item.prefix))
      setStep(2)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Could not preview this API.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleIngest = async () => {
    setError(null)
    setIsLoading(true)
    try {
      const result = await createProvider({
        ...source,
        id: providerId,
        name: name.trim(),
        path_prefixes: selectedPrefixes,
      })
      setJobId(result.job_id)
      setStep(3)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Could not start ingestion.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleDone = useCallback(
    async (completedProviderId: string) => {
      await onComplete(completedProviderId)
      onClose()
    },
    [onClose, onComplete],
  )

  return (
    <div className="add-api-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && step !== 3) onClose()
    }}>
      <section className="add-api-modal" role="dialog" aria-modal="true" aria-labelledby="add-api-title">
        <header className="add-api-header">
          <div>
            <h2 id="add-api-title">Add an API</h2>
            <p>Connect any valid OpenAPI 3.0 or 3.1 specification.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close add API dialog" disabled={step === 3}>
            <X size={18} />
          </button>
        </header>

        <ol className="add-api-steps" aria-label="Progress">
          {['Source', 'Configure', 'Ingest'].map((label, index) => {
            const number = index + 1
            return <li key={label} data-active={step === number} data-complete={step > number}>{step > number ? '✓' : number} {label}</li>
          })}
        </ol>

        <div className="add-api-content">
          {step === 1 && (
            <ApiSourceStep
              sourceType={sourceType}
              setSourceType={setSourceType}
              url={url}
              setUrl={setUrl}
              specContent={specContent}
              setSpecContent={setSpecContent}
              fileName={fileName}
              setFileName={setFileName}
              error={error}
              isLoading={isLoading}
              onNext={() => void handlePreview()}
              onCancel={onClose}
            />
          )}
          {step === 2 && preview && (
            <ApiPreviewStep
              preview={preview}
              providerId={providerId}
              name={name}
              selectedPrefixes={selectedPrefixes}
              setProviderId={setProviderId}
              setName={setName}
              setSelectedPrefixes={setSelectedPrefixes}
              error={error}
              isLoading={isLoading}
              onBack={() => { setError(null); setStep(1) }}
              onIngest={() => void handleIngest()}
            />
          )}
          {step === 3 && jobId && (
            <ApiIngestStep jobId={jobId} onDone={handleDone} onBack={() => { setError(null); setStep(2) }} />
          )}
        </div>
      </section>
    </div>
  )
}
