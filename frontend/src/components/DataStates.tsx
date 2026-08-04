import './DataStates.css'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <p className="data-state data-state-loading" role="status">
      {label}
    </p>
  )
}

export function ErrorState({ message }: { message: string }) {
  return (
    <p className="data-state data-state-error" role="alert">
      {message}
    </p>
  )
}

export function EmptyState({ message }: { message: string }) {
  return <p className="data-state data-state-empty">{message}</p>
}
