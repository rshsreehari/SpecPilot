import { useEffect } from 'react'
import { AnswerCard } from '../components/AnswerCard'
import { useAppShell } from '../context/useAppShell'
import './AskScreen.css'

const EXAMPLE_QUESTIONS = [
  'Which endpoint creates a new resource, and which fields are required?',
  'What authentication headers does this API require?',
  'Plan the steps to create, update, and then retrieve a resource.',
]

export function AskScreen() {
  const {
    setScreenContext,
    providers,
    selectedProviderId,
    panel,
    conversation,
    setAssistantDraft,
    openAddApi,
  } = useAppShell()

  useEffect(() => {
    setScreenContext({ screen: 'ask', providerId: selectedProviderId ?? undefined })
  }, [setScreenContext, selectedProviderId])

  const ingestedProviders = providers.filter((provider) => provider.ingested)
  const providerName = providers.find((provider) => provider.id === selectedProviderId)?.name
  const latest = conversation.turns.at(-1)
  const history = conversation.turns.slice(0, -1).reverse()

  if (ingestedProviders.length === 0) {
    return (
      <section className="ask-screen ask-screen-onboarding">
        <span className="ask-screen-eyebrow">Start here</span>
        <h1>Connect an API before asking questions</h1>
        <p>Paste an OpenAPI URL or upload its JSON/YAML specification. SpecPilot will make every endpoint searchable and mechanically verify the answers it gives.</p>
        <button type="button" className="ask-screen-primary-action" onClick={openAddApi}>Add your first API</button>
      </section>
    )
  }

  return (
    <section className="ask-screen">
      <div className="ask-screen-intro">
        <span className="ask-screen-eyebrow">Spec-checked API answers</span>
        <h1>{providerName ? `${providerName} API workspace` : 'Ask across your APIs'}</h1>
        <p>SpecPilot retrieves the relevant OpenAPI operations, generates a practical answer, and checks every cited endpoint against the source specification.</p>
        <p>HTTP methods are simple; real APIs are not. The value is finding exact paths, parameters, request bodies, constraints, and multi-step sequences without inventing them.</p>
      </div>

      {!latest ? (
        <div className="ask-screen-first-run">
          <h2>Ask from the assistant panel</h2>
          <p>Use Quick for a fast lookup or Agent when the task needs several connected API operations.</p>
          <div className="ask-screen-examples">
            {EXAMPLE_QUESTIONS.map((question) => (
              <button key={question} type="button" onClick={() => { setAssistantDraft(question); panel.open() }}>
                {question}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <AnswerCard turn={latest} providers={providers} />
      )}

      {history.length > 0 && (
        <div className="ask-screen-history">
          <div className="ask-screen-history-heading">
            <h2>Previous answers</h2>
            <button type="button" onClick={conversation.clear}>Clear</button>
          </div>
          {history.map((turn) => <AnswerCard key={turn.id} turn={turn} providers={providers} />)}
        </div>
      )}
    </section>
  )
}
