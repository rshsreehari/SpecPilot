import { useRef, type DragEvent } from 'react'
import type { ProviderSourceType } from '../../lib/types'
import { EXAMPLE_SPECS } from './exampleSpecs'

interface ApiSourceStepProps {
  sourceType: ProviderSourceType
  setSourceType: (type: ProviderSourceType) => void
  url: string
  setUrl: (url: string) => void
  specContent: string
  setSpecContent: (content: string) => void
  fileName: string
  setFileName: (name: string) => void
  error: string | null
  isLoading: boolean
  onNext: () => void
  onCancel: () => void
}

export function ApiSourceStep(props: ApiSourceStepProps) {
  const fileInput = useRef<HTMLInputElement>(null)

  const readFile = (file: File) => {
    props.setFileName(file.name)
    void file.text().then(props.setSpecContent).catch(() => props.setSpecContent(''))
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    const file = event.dataTransfer.files[0]
    if (file) readFile(file)
  }

  const canContinue =
    props.sourceType === 'url' ? Boolean(props.url.trim()) : Boolean(props.specContent)

  return (
    <>
      <div className="add-api-tabs" role="tablist" aria-label="API source">
        <button
          type="button"
          role="tab"
          aria-selected={props.sourceType === 'url'}
          data-active={props.sourceType === 'url'}
          onClick={() => props.setSourceType('url')}
        >
          From URL
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={props.sourceType === 'upload'}
          data-active={props.sourceType === 'upload'}
          onClick={() => props.setSourceType('upload')}
        >
          Upload file
        </button>
      </div>

      {props.sourceType === 'url' ? (
        <div className="add-api-field">
          <label htmlFor="add-api-url">OpenAPI URL</label>
          <input
            id="add-api-url"
            type="url"
            value={props.url}
            onChange={(event) => props.setUrl(event.target.value)}
            placeholder="https://example.com/openapi.json"
            autoFocus
          />
          <p>The SpecPilot backend fetches and validates this URL.</p>
          <div className="add-api-examples" aria-label="Example API specifications">
            <span>Try an example</span>
            <div>
              {EXAMPLE_SPECS.map((example) => (
                <button key={example.name} type="button" onClick={() => props.setUrl(example.url)}>
                  {example.name}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div
          className="add-api-dropzone"
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
        >
          <input
            ref={fileInput}
            type="file"
            accept=".json,.yaml,.yml,application/json,application/yaml,text/yaml"
            className="sr-only"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) readFile(file)
            }}
          />
          <strong>{props.fileName || 'Drop an OpenAPI file here'}</strong>
          <span>.json, .yaml, or .yml · up to 50 MB</span>
          <button type="button" onClick={() => fileInput.current?.click()}>
            Choose file
          </button>
        </div>
      )}

      {props.error && <p className="add-api-error" role="alert">{props.error}</p>}
      <div className="add-api-actions">
        <button type="button" className="add-api-secondary" onClick={props.onCancel}>Cancel</button>
        <button type="button" disabled={!canContinue || props.isLoading} onClick={props.onNext}>
          {props.isLoading ? 'Checking…' : 'Preview API'}
        </button>
      </div>
    </>
  )
}
