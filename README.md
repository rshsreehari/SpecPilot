# SpecPilot

**Point this at any OpenAPI 3.x spec - a public URL or a local file - and it answers
questions about that API, then mechanically checks every citation against the spec's own
machine-readable definition.** No LLM ever grades another LLM; hallucination becomes a
measured number instead of an impression, for whichever API you hand it. This is not a
Stripe tool or a GitHub tool - it's a generic evaluation platform for API documentation.

Three examples ship pre-ingested so there's something real to look at immediately -
**Stripe, GitHub, and OpenAI: 3 providers, 446 endpoints combined, 80 hand-written eval
questions between them.** They are examples, not the boundary of what the app does. Four
more public specs (Petstore, Twilio, DigitalOcean's 659-endpoint API, Plaid's 335-endpoint
API) are one click away in the in-app **Add API** flow right now, and any other public
OpenAPI 3.x URL or uploaded file works the same way - no code change, no new provider-
specific parsing. See [Bring your own API](#bring-your-own-api) below for exactly how, or
jump straight to the
[ingestion pipeline walkthrough](docs/ARCHITECTURE.md#1-provider-preview-and-ingestion) to
see the parser handling three structurally different real specs today.

This README is the complete guide to running SpecPilot yourself, from a clean Mac, with
your own LLM API key. For the full technical architecture, see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). For the story of how this was built
phase by phase, see [`docs/HISTORY.md`](docs/HISTORY.md). For what's currently known-broken
or intentionally out of scope, see [`BUGS.md`](BUGS.md).

**A word on "provider" - this is the one thing worth being precise about up front**, because
the two meanings are easy to conflate on a skim: an **API provider** (Stripe, GitHub,
OpenAI, or any spec you add) is a configured OpenAPI document SpecPilot ingests and answers
questions about - this is **unbounded**, see [Bring your own API](#bring-your-own-api). The
**LLM provider** is Mistral - the one model SpecPilot's backend calls to *generate* an
answer, unrelated to which APIs it can document - see
[A note on the LLM provider](#a-note-on-the-llm-provider-separate-from-api-scope). Adding a new API provider never
touches which LLM answers the question, and which LLM answers the question never limits
which APIs can be added.

## Any OpenAPI spec, not a fixed list

What actually makes this generic, not just described as generic:

- **Ingestion is spec-driven, not provider-driven.** `src/ingest/parse.py` resolves
  `$ref` pointers of any depth, merges `allOf`/`anyOf`/`oneOf` composition, reads
  parameters from both the `parameters` array and every `requestBody` media type, handles
  OpenAPI 3.1's array-valued `type`, and synthesizes an `operationId` when the spec omits
  one. None of that is Stripe-specific - it was generalized and proven against GitHub's
  and OpenAI's very differently-shaped specs, then against Petstore, Twilio, DigitalOcean,
  and Plaid on top of that.
- **Adding a provider is a product feature, not a code change.** Paste a URL, upload a
  `.json`/`.yaml`/`.yml` file, or run `specpilot ingest --url/--file` from the CLI - see
  [Bring your own API](#bring-your-own-api). There is no per-provider branch anywhere in
  the ingestion, retrieval, answering, or grading code.
- **Retrieval, answering, and mechanical grading are identical for every provider.** The
  same four retrieval strategies, the same `Truth`-based citation verification, and the
  same eval harness run against Stripe, GitHub, OpenAI, or whatever you add next - just
  write `eval/questions/<your-id>.yaml` and every `eval`/`compare` command works
  immediately, no harness changes.

## Headline number

Retrieval turns an LLM that's frequently wrong about which endpoint exists into one
that's essentially never wrong about it - and the size of that effect differs by API,
which is itself the interesting result:

| Provider | Mode | Endpoint accuracy | Parameter hallucination |
|---|---|---|---|
| Stripe (dev, n=25) | No retrieval | 93% (n=28) | 21% (n=33) |
| Stripe (dev, n=25) | Reranked retrieval | 100% (n=40) | 0% (n=5) |
| GitHub (dev, n=10) | No retrieval | 82% (n=11) | 77% (n=13) |
| GitHub (dev, n=10) | Hybrid retrieval | 100% (n=7) | 0% (n=9) |

GitHub's no-retrieval baseline hallucinates parameters far more (77%) than Stripe's (21%)
- the model's memorized knowledge of GitHub's exact parameter names is evidently weaker,
so retrieval buys proportionally more there. That's not a number you'd get from testing
against one API and calling it done. Full per-strategy tables are in
[`eval/reports/`](eval/reports/) and live in the app's **Evaluation** screen, with a
provider tab per API, once you've ingested and run one yourself (see
[Reproduce the eval](#reproduce-the-eval) below).

**Caveat, stated plainly:** these are dev-split numbers, and GitHub's is a single
strategy (hybrid) rather than the full four-way comparison Stripe has - see `STATE.md`
for exactly what's been run and what a full `compare --all-providers` still needs. Holdout
splits are deliberately unrun for every provider - this project's rule is never to tune
anything against holdout, and the honest way to keep that rule is to not even look at
holdout until there's nothing left to tune. Stripe's parameter-hallucination column also
has a small sample under retrieval (n=5); see `BUGS.md` B-006 before citing it as decisive.

## A note on the LLM provider (separate from API scope)

This section is about which model *answers* questions, not which APIs you can point
SpecPilot at - that part is unlimited, see above. SpecPilot's backend calls **Mistral's
API** specifically (`src/answer/mistral_client.py`) to generate answers. It is not
currently LLM-provider-agnostic - there is no config flag to point it at OpenAI,
Anthropic, or a local model instead; that's a deliberate, disclosed scope choice
(`CLAUDE.md`: one LLM provider, kept simple on purpose), not a technical ceiling on how
many *documentation* APIs it can ingest. You will need a Mistral API key to run the parts
of this app that generate answers (`/query`, `/agent/query`, the eval commands).
Everything else - browsing ingested endpoints, viewing an already-generated report - works
without one, but you need a key to produce new answers or new reports yourself.

Getting one is free and takes about two minutes:

1. Go to **[console.mistral.ai](https://console.mistral.ai)** and create an account.
2. Open **API Keys** in the left sidebar and click **Create new key**.
3. Copy the key - you'll paste it into `.env` in step 4 below.

The free tier's rate limit is low enough that bulk evaluation runs (`specpilot eval`,
`specpilot compare`) take much longer than you'd expect from the number of questions - this
is documented, expected, and not a sign anything is broken. See `BUGS.md` B-005. Asking
single questions through the UI is unaffected by this.

## Prerequisites (macOS)

| Tool | Check if installed | Install if missing |
|---|---|---|
| Docker Desktop | `docker --version` | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| Python 3.12+ | `python3 --version` | `brew install python@3.12` |
| uv | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node 20+ | `node --version` | `brew install node@20` |
| git | `git --version` | `brew install git` |

Open Docker Desktop at least once and make sure it's actually running (the whale icon in
your menu bar) before continuing - every command below that touches the database needs it.

## Step-by-step setup

### 1. Get the code

```bash
git clone <url-of-your-fork-or-remote> specpilot
cd specpilot
```

(If you already have this folder locally rather than a remote to clone, just `cd` into it
- everything below is identical either way.)

### 2. Configure your API key

```bash
cp .env.example .env
```

Open `.env` in an editor and fill in the key you created above:

```
MISTRAL_API_KEY=your-key-here
DATABASE_URL=postgresql+asyncpg://postgres:specpilot@localhost:5432/specpilot
```

Leave `DATABASE_URL` as-is unless you already have something else running on port 5432 -
it matches the Postgres container the next step starts. **Never commit `.env`** - it's
already in `.gitignore`.

### 3. Install backend dependencies

```bash
uv sync
```

This creates a `.venv/` and installs everything in `pyproject.toml` (FastAPI,
SQLAlchemy, the Mistral SDK, sentence-transformers for local embeddings, etc.) - no
separate `pip install` step needed.

### 4. Start Postgres and run migrations

```bash
make db-up
```

This starts a `pgvector/pgvector:pg16` container named `specpilot-db` (creating it the
first time, reusing it after), waits until Postgres is actually ready to accept
connections, and then runs every Alembic migration. You should see `OK db-up` at the end.

### 5. Ingest the configured APIs

```bash
make ingest
```

Ingests every provider listed in [`specs.yaml`](specs.yaml) - by default Stripe, GitHub,
and OpenAI. For each one: downloads its public OpenAPI spec (or reads a local file),
caches it under `data/specs/`, parses out the configured subset, and embeds each endpoint
locally with `sentence-transformers` - no API key needed for this step, and no cost. Takes
under a minute on a normal connection. Safe to re-run any time; it's idempotent, and
re-ingesting one provider never touches another's data.

```bash
uv run specpilot providers list
```

should show all three as `ingested`, with real endpoint counts.

### 6. Start the backend

```bash
make dev
```

FastAPI is now running at `http://localhost:8000`. Leave this running and open a **new
terminal tab** for the next step.

Quick sanity check in a third terminal, any time:
```bash
curl -s localhost:8000/health
# {"status":"ok"}
```

### 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Vite starts on `http://localhost:5173` and proxies API calls to the backend on `:8000`
(see `frontend/vite.config.ts` if you need to change either port). **Open
`http://localhost:5173` in your browser** - you should see the Ask screen.

### 8. Try it

Pick a provider from the selector in the header (or leave it on "All providers"), then
use the full-height **API Assistant** on the right. **Quick** performs one focused
retrieval; **Agent** can chain several endpoint/parameter lookups for a multi-step task
and shows those tool calls as they happen. Try *"How do I create a subscription with a
14 day trial period?"* (Stripe) or *"How do I create a pull request?"* (GitHub). The
same answer appears as a readable result in the main area with citation chips - green if
the endpoint exists in the selected provider's spec, red if not.

The **Evaluation** screen will say there are no reports yet until you run one - see the
next section. The **Endpoints** screen works immediately; it's just browsing what got
ingested in step 5, filterable by provider.

## Reproduce the eval

This is the actual point of the project - not just answering questions, but measuring
whether the answers are trustworthy, for whichever API you point it at.

```bash
# One provider, one retrieval strategy vs. the no-retrieval baseline (a few minutes)
uv run specpilot eval --provider stripe --split dev --seed 42 --strategy reranked
uv run specpilot eval --provider github --split dev --seed 42 --strategy hybrid

# One provider, all four retrieval strategies compared side by side (much slower - see
# the rate-limit note above; budget 30-45 minutes on a free-tier key)
uv run specpilot compare --provider stripe --split dev --seed 42

# Every configured provider, pooled into one combined table AND a per-provider
# breakdown - this is the "does the effect size differ by API?" question, and it's the
# slowest command here (roughly the sum of running compare on each provider separately)
uv run specpilot compare --all-providers --split dev --seed 42

# The agent (multi-step, tool-calling) vs. single-pass retrieval, on one provider's
# harder multi-step questions
uv run specpilot eval --provider stripe --split dev --seed 42 --mode agent
```

Each command writes a JSON + Markdown report into `eval/reports/`. Refresh the
**Evaluation** screen in the browser afterward - it reads those files directly through
`GET /api/reports`, no restart needed; an `--all-providers` report shows a "Combined" tab
plus one tab per provider, since a pooled percentage alone can hide which provider a
strategy actually helps most. Grading is always mechanical (string/set comparison
against the spec) - never an LLM judging another LLM's output; that's the one rule this
project treats as non-negotiable, for every provider.

Don't run `--split holdout` unless you mean it: this project's discipline is to never look
at holdout results while still able to change anything based on them. Reserve it for the
very end.

## Bring your own API

This is the actual scope of the app, not an add-on: Stripe/GitHub/OpenAI are three
pre-loaded examples, and everything below has already been run against four more real,
unrelated specs (Petstore, Twilio, DigitalOcean, Plaid) to prove the parser and pipeline
don't assume any one API's shape. The primary flow is in the app; no terminal or
hand-editing `specs.yaml`:

1. Click **Add API** in the header (or on the empty Ask/API screen).
2. Paste a public OpenAPI URL, choose one of the verified examples, or upload a
   `.json`/`.yaml`/`.yml` file.
3. Review the detected title, OpenAPI version, endpoint count, sample paths, and parser
   warnings before anything is written.
4. Edit the provider ID/name and optionally deselect path-prefix groups. Large specs show
   a filtering hint, but filtering is never forced.
5. Click **Ingest API** and watch the real download/parse/embedding stages. When it
   finishes, the provider is selected automatically and behaves like every bundled one.

> **Screenshot placeholder:** Add API modal showing Source → Configure → Ingest. Replace
> this block with the final product screenshot before publishing the portfolio version.

The URL is fetched by the backend (not the browser), with a 30-second timeout, at most
three redirects, and a 50 MB limit. JSON versus YAML is detected from content. Swagger
2.0 and malformed/non-OpenAPI documents return specific errors in the modal rather than
a generic failure.

Petstore, Twilio, DigitalOcean, and Plaid are included as one-click examples; every URL
was fetched and parsed with SpecPilot's own OpenAPI 3.x parser before it was added.

The **APIs** screen shows source, endpoint count, ingestion time, and evaluation-question
status. Deletion names the provider and endpoint count before removing only that
provider's config and database rows.

### Scripting path

The CLI remains available for automation:

```bash
# From a URL
uv run specpilot ingest --url https://example.com/openapi.json --id acme --name "Acme"

# From a local file (works for either JSON or YAML - detected by content, not extension)
uv run specpilot ingest --file ./my-api-spec.yaml --id my-api --name "My API"
```

Either command appends the provider to `specs.yaml` and ingests it immediately - it
shows up in `specpilot providers list`, the provider selector in the frontend, and every
CLI command's `--provider` flag right away. Requirements:

- **OpenAPI 3.0 or 3.1.** Swagger 2.0 is explicitly rejected with a clear error - it's out
  of scope, not silently mis-parsed.
- URL and UI-uploaded documents are capped at 50 MB. GitHub's issues+pulls subset (79
  endpoints), OpenAI's full 288-endpoint spec, DigitalOcean's 659-endpoint spec, and
  Plaid's 335-endpoint spec all fit comfortably.

To remove a provider (config entry and every row it owns in the database):

```bash
uv run specpilot providers remove acme
```

Once ingested, write yourself a small `eval/questions/<id>.yaml` (copy the shape of
`eval/questions/github.yaml` - a handful of answerable questions with their real expected
endpoint, a couple of multi-endpoint ones, a couple of genuinely-unanswerable negative
controls) and every `eval`/`compare` command above works against it immediately.

## Running the whole thing in Docker instead

If you'd rather not install Node/Python locally at all, everything except the database can
run in one container:

```bash
# Postgres still needs to exist somewhere reachable - reuse the same one from step 4:
make db-up

# Build the image (multi-stage: builds the frontend, installs Python deps, then a slim
# non-root runtime - takes a few minutes the first time)
docker build -t specpilot .

# Connect it to the same Docker network as specpilot-db, or point DATABASE_URL at any
# reachable pgvector-enabled Postgres:
docker network create specpilot-net 2>/dev/null || true
docker network connect specpilot-net specpilot-db 2>/dev/null || true

docker run -d --name specpilot-app --network specpilot-net \
  -e DATABASE_URL="postgresql+asyncpg://postgres:specpilot@specpilot-db:5432/specpilot" \
  -e MISTRAL_API_KEY="your-key-here" \
  -p 8000:8000 \
  specpilot
```

Open `http://localhost:8000` - the same FastAPI process serves both the API and the built
frontend. Run `make ingest` (against the same database, from your host, with `uv` still
installed) at least once before querying - the spec cache and embeddings aren't baked into
the image, only the code is.

```bash
curl -s localhost:8000/health
curl -s localhost:8000/metrics | head       # Prometheus-format metrics
```

## Verifying everything works

```bash
make check
```

Runs `ruff`, the full backend pytest suite with coverage (enforced at 80%), frontend lint
and Vitest interaction tests, a strict TypeScript production build, and a smoke test
against a live server. This is the same check the project holds itself to after every
phase - if it is not green, treat that as a real problem, not a formality.

## HOW TO RUN?
Starting it in 3 terminal tabs:

cd to specpilot

# Tab 1
make db-up        # wait for "OK db-up"

# Tab 2
make dev          # backend on :8000, leave running

# Tab 3
cd frontend && npm run dev    # :5173, leave running

# Tab 4 — your working tab
open http://localhost:5173

## Troubleshooting

- **`make db-up` hangs on "Waiting for Postgres..."** - Docker Desktop probably isn't
  actually running yet. Open the app, wait for the whale icon to stop animating, retry.
- **`uv: command not found` after installing** - restart your terminal (the installer
  modifies your shell profile, which only takes effect in new shells).
- **Port 5432 already in use** - something else on your Mac is already using Postgres's
  default port. Either stop that service, or change the port in both `make db-up`'s
  `docker run` line (`Makefile`) and `DATABASE_URL` in `.env` to match.
- **`/query` returns a 401/403 from Mistral, or times out** - double-check `MISTRAL_API_KEY`
  in `.env` has no extra quotes or whitespace, and that the key is active in the Mistral
  console.
- **A bulk `eval`/`compare` run seems stuck** - it's very likely rate-limited, not stuck.
  Check the logs for `429` responses; this key's tier genuinely takes this long (see
  `BUGS.md` B-005). Single questions through the UI are unaffected.
- **Frontend shows a network error / can't reach the API** - confirm `make dev` is still
  running in its terminal tab, and that you're browsing `localhost:5173` (the Vite dev
  server), not `:8000` directly, if you're running the local-dev setup rather than Docker.
- **Evaluation screen says "No eval reports yet"** - expected until you run one of the
  commands in [Reproduce the eval](#reproduce-the-eval); it reads real files from
  `eval/reports/`, nothing is pre-seeded.

## Architecture

```mermaid
flowchart TB
    subgraph Ingest["Ingest (per provider: specs.yaml)"]
        Spec["any OpenAPI 3.x spec -\nStripe / GitHub / OpenAI / yours"] --> Parse[parse + chunk + embed]
        Parse --> DB[(Postgres + pgvector\nprovider_id on every row)]
    end

    subgraph Retrieval["Retrieval, scoped by provider_id"]
        Naive["naive: cosine similarity\n(single query, any/all providers)"]
        BM25["bm25: one Okapi index PER PROVIDER,\nfused by RRF if none specified"]
        Hybrid[hybrid: RRF fusion of naive+bm25]
        Reranked[reranked: cross-encoder]
    end
    DB --> Naive & BM25 & Hybrid & Reranked

    subgraph Answering
        Naive & BM25 & Hybrid & Reranked --> Mistral[Mistral chat completion]
        Mistral --> Answer["answer + code_snippet +\ncitations (each tagged with a provider)"]
    end

    subgraph Grading
        Answer --> Truth["Truth: mechanical spec check,\nper provider"]
        Truth --> Metrics[endpoint_accuracy, hallucination rate,\nrecall, MRR, refusal rate...]
    end

    subgraph Agent
        AgentLoop[agent loop: search_docs, get_endpoint,\nlist_parameters, find_related]
        AgentLoop --> Mistral
        AgentLoop -. also exposed via .-> MCP[MCP server]
    end

    subgraph Frontend[React frontend]
        ProviderSel[Provider selector]
        Ask[Ask screen]
        Eval["Evaluation screen\n(per-provider tabs)"]
        Endpoints[Endpoint browser]
        APIs[Add/manage API flow]
        Panel["Full-height assistant:\nQuick + Agent"]
    end
    Answer --> Ask
    Metrics --> Eval
    DB --> Endpoints
    AgentLoop -- SSE --> Panel
    APIs --> Parse
    ProviderSel -.-> Ask & Eval & Endpoints & Panel
```

This is the condensed version. Full component breakdown, database schema, retrieval
strategy internals, and the deployment diagram are all in
**[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)**.

## What's where

- `specs.yaml` - configured API providers (id, name, spec URL or managed/local path,
  `path_prefixes`, bundled/runtime origin). The UI and CLI scripting paths both persist
  ordinary entries here.
- `src/providers.py` - loads/validates `specs.yaml`, appends ad hoc providers.
- `src/ingest/` - downloads (or reads locally) and parses any OpenAPI 3.x spec - JSON or
  YAML, detected by content - chunks one passage per endpoint, embeds locally
  (`sentence-transformers`, no API cost). Generalized to handle `allOf`/`anyOf`/`oneOf`
  composition, every request-body media type, OpenAPI 3.1's array-valued `type`, and
  missing `operationId`, not just Stripe's shape.
- `src/retrieval/` - four strategies behind one `Retriever` protocol, all provider-scoped:
  naive (cosine), BM25 (hand-rolled Okapi - one index **per provider**, never pooled, see
  `docs/ARCHITECTURE.md` for why that matters), hybrid (reciprocal rank fusion), reranked
  (local cross-encoder).
- `src/answer/` - the shared answer-generation path used by both `/query` and the eval
  harness; Mistral client with retry/backoff.
- `src/eval/` - ground truth extraction from the spec (per provider), mechanical grading,
  metrics, the eval/compare/agent-eval runners (single-provider and all-providers), and
  report building. Questions live in `eval/questions/<provider_id>.yaml`.
- `src/agent/` - the tool-calling agent loop (`search_docs`, `get_endpoint`,
  `list_parameters`, `find_related`), each provider-aware, and its SSE event stream.
- `src/mcp_server.py` - the same four tools exposed over the Model Context Protocol; see
  `docs/mcp-demo.md` for a real transcript against a generic MCP client.
- `src/api/` - FastAPI app: `/query`, `/agent/query`, `/agent/stream/{id}` (SSE, all
  accepting an optional `provider_id`); provider preview/create/job/delete endpoints;
  `/api/reports`, `/api/endpoints`, `/metrics`, and `/health`.
- `frontend/` - React 18 + TypeScript + TanStack Query. Ask, Evaluation, Endpoints, and
  APIs screens; the three-step Add API modal; and one full-height, responsive assistant
  rail. Quick and Agent share one conversation/history instead of competing answer
  inputs.
- `docs/HISTORY.md` - the full, chronological story of how this project was built.
- `docs/ARCHITECTURE.md` - the full technical architecture.

## Limitations

This project keeps a running, honest list of known bugs and deliberate scope decisions in
`BUGS.md` rather than hiding them. Highlights:

- Holdout splits intentionally unrun, for every provider (see above).
- SSE streams the final answer as one token event, not word-by-word - tool-call
  visibility (`tool_start`/`tool_end`) is real streaming; answer text is not.
- The side panel's Stop button ends the browser's connection but doesn't cancel the
  server-side agent loop mid-flight (B-011).
- No auth/multi-tenancy, no doc versioning, single LLM provider (Mistral) - all out of
  scope by design, see `CLAUDE.md`. Multiple *API* providers are explicitly in scope now;
  this line is about auth/users/versioning/LLM choice, not about API specs.
- Each configured provider ingests a `path_prefixes`-scoped subset of its real spec by
  default (a speed choice - see `specs.yaml`), except OpenAI, whose entire 288-endpoint
  spec is ingested with no filtering at all.
- The Docker image is large (~6GB) because local embeddings/reranking pull in
  `torch`/`transformers`; not yet slimmed to a CPU-only wheel.

See `STATE.md` for what's built phase-by-phase and `BUGS.md` for the full, itemized list.
