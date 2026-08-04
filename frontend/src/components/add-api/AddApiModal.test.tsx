import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createProvider, getProviderJob, previewProvider } from '../../lib/api'
import { AddApiModal } from './AddApiModal'

vi.mock('../../lib/api', () => ({
  createProvider: vi.fn(),
  getProviderJob: vi.fn(),
  previewProvider: vi.fn(),
}))

const PREVIEW = {
  openapi_version: '3.1.0',
  title: 'Widget API',
  endpoint_count: 12,
  sample_paths: ['/v1/widgets'],
  detected_tags: ['Widgets'],
  path_prefixes: [{ prefix: '/v1', endpoint_count: 12 }],
  warnings: [],
}

describe('AddApiModal', () => {
  beforeEach(() => {
    vi.mocked(previewProvider).mockReset()
    vi.mocked(createProvider).mockReset()
    vi.mocked(getProviderJob).mockReset()
  })

  it('moves through source, preview, and ingestion steps', async () => {
    vi.mocked(previewProvider).mockResolvedValue(PREVIEW)
    vi.mocked(createProvider).mockResolvedValue({ job_id: 'job-1', provider_id: 'widget-api' })
    vi.mocked(getProviderJob).mockResolvedValue({
      job_id: 'job-1',
      provider_id: 'widget-api',
      status: 'embedding',
      progress: { current: 6, total: 12, stage_label: 'Embedding 6 of 12' },
      endpoint_count: null,
      skipped: [],
      warnings: [],
      error: null,
    })

    render(<AddApiModal onClose={vi.fn()} onComplete={vi.fn().mockResolvedValue(undefined)} />)
    fireEvent.change(screen.getByLabelText('OpenAPI URL'), {
      target: { value: 'https://example.com/openapi.json' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Preview API' }))

    expect(await screen.findByText('12 endpoints')).toBeInTheDocument()
    expect(screen.getByLabelText('Provider ID')).toHaveValue('widget-api')
    fireEvent.click(screen.getByRole('button', { name: 'Ingest API' }))

    expect(await screen.findByText('Embedding 6 of 12')).toBeInTheDocument()
    await waitFor(() => expect(createProvider).toHaveBeenCalledWith(expect.objectContaining({ id: 'widget-api' })))
  })

  it('renders the exact preview error and stays on the source step', async () => {
    vi.mocked(previewProvider).mockRejectedValue(
      new Error('The document declares Swagger 2.0; only OpenAPI 3.x is supported.'),
    )

    render(<AddApiModal onClose={vi.fn()} onComplete={vi.fn().mockResolvedValue(undefined)} />)
    fireEvent.change(screen.getByLabelText('OpenAPI URL'), {
      target: { value: 'https://example.com/swagger.json' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Preview API' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Swagger 2.0')
    expect(screen.getByRole('button', { name: 'Preview API' })).toBeInTheDocument()
  })
})
