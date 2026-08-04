import type { ConversationTurn, Provider } from '../lib/types'
import { CitationChip } from './CitationChip'
import { ErrorState, LoadingState } from './DataStates'

export function AnswerCard({ turn, providers }: { turn: ConversationTurn; providers: Provider[] }) {
  return (
    <article className="ask-screen-answer">
      <header className="ask-screen-answer-header">
        <div>
          <span>{turn.mode === 'agent' ? 'Agent workflow' : 'Quick answer'}</span>
          <h2>{turn.question}</h2>
        </div>
        {turn.status === 'done' && <span className="ask-screen-answer-status">Checked</span>}
      </header>

      {turn.status === 'working' && <LoadingState label={turn.mode === 'agent' ? 'The agent is inspecting the API…' : 'Searching the API specification…'} />}
      {turn.status === 'failed' && <ErrorState message={turn.error ?? 'The request failed.'} />}
      {turn.answer && (
        <>
          <p className="ask-screen-answer-text">{turn.answer.answer}</p>
          {turn.answer.code_snippet && (
            <pre className="ask-screen-code"><code>{turn.answer.code_snippet}</code></pre>
          )}
          {turn.answer.citations.length > 0 ? (
            <div>
              <p className="ask-screen-verification-label">Checked against the provider&apos;s OpenAPI spec</p>
              <div className="ask-screen-citations">
                {turn.answer.citations.map((citation) => (
                  <CitationChip
                    key={`${citation.provider_id}-${citation.method}-${citation.path}`}
                    citation={citation}
                    showProvider={providers.length > 1}
                  />
                ))}
              </div>
            </div>
          ) : (
            <p className="ask-screen-no-citations">No endpoint citations were returned for this answer.</p>
          )}
        </>
      )}
    </article>
  )
}
