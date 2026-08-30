# CLAUDE.md — Spark MVP

Guidance for Claude Code working in this repository. Read `docs/ARCHITECTURE.md` for the full design; this file is how we build it.

---

## What we are building

One anonymous three-minute voice call a day, with one person whose path crossed yours today. Identity revealed only on mutual consent. The system then stays with the connection for weeks.

**MVP scope — the one experience that must work end to end:**

```
onboarding → daily overlap match → anonymous encounter → 3-minute call
          → mutual reveal → lock-in with continuity over simulated weeks
```

Everything is **simulated**. No real users, no real Singpass integration, no real telephony, no real location data. The onboarding verification screen is an explicitly labelled, data-free concept; the voice bridge is a mock. The demo is a recorded simulation run, not a live system.

**Submission: 7 Sep 2026. One submission only — there is no second attempt.**

---

## Non-negotiable invariants

These are the product. If a change would weaken one, stop and ask rather than implementing it.

1. **No identity, photo, or number is exposed before both parties say yes after the call.**
2. **A decline emits no observable signal to the other party** — no count, no timing difference, no delay, nothing inferable.
3. **No distance, place name, coordinate, or map position is ever rendered to a user.** Overlap is coarse cell + time bucket, historical only.
   *Narrow exception, post-reveal only:* the Date Agent names KINDS of place
   ("a hawker centre") once two people have mutually revealed and are choosing
   where to meet. It is never given a cell, coordinate, distance or overlap
   history, so "near where you both were" cannot be built. ARCHITECTURE §13.6.
4. **The call terminates at 180 seconds** regardless of state. That is a
   MAXIMUM, not a minimum — either person may leave sooner, and the exit is
   shared with the timer so nothing downstream can tell the two apart.
5. **Consent events are append-only** and never joined into anything user-visible.
6. **No model decides any of the above.** Consent, eligibility and identity-reveal are ordinary Python with tests. A model must never be the only thing standing between a stranger and someone's identity.

Each invariant has a test in `tests/test_consent.py`. **Never delete or weaken one of those tests to make a feature pass.** If a test blocks you, the feature is wrong.

---

## Commands

```bash
cd spark
uv sync                                  # base install
uv sync --extra aws                      # + Bedrock
cp .env.example .env                     # then fill in keys — never commit .env

uv run -m src.cli.simulate --weeks 6     # full simulation run
uv run -m src.cli.encounter --seed 42    # one encounter, verbose trace
uv run -m eval.run_arms                  # Spark vs random vs similarity
uv run -m eval.report                    # emits metric tables for the slides

uv run -m src.api                        # the HTTP API on :8000
uv run pytest                            # all tests (272 passed, 1 skipped)
uv run pytest tests/test_consent.py -v   # the invariants — run before every commit

cd ../web                                # the demo client
npm install && npm run dev               # :5173, no backend needed
npm test                                 # UI invariants 1-7 (200 passed)
```

Running both together, and what is still stubbed: `docs/PILOT.md`.

---

## Layout

```
spark/
  src/
    graph/      LangGraph supervisor, nodes, state machine
    agents/     one module per agent
    mcp/        the six MCP servers
    api/        the HTTP layer — a thin wrapper over the graph, not a second one
    schemas/    pydantic models — every agent output has one
    telemetry/  OTEL setup, metric collectors
  data/         synthetic personas, adversarial safety set
  tests/        invariants first, then everything else
  eval/         the three-arm harness
web/            the demo client (Vite + React). See docs/FRONTEND.md
docs/           ARCHITECTURE.md, FRONTEND.md, PILOT.md, PROPOSAL.docx
```

Judges are told to check whether *"presentation methodology is reflected at code level."* Keep the supervisor graph, the consent interrupt, and the tool definitions easy to find and commented. Someone should be able to open `src/graph/` and see the architecture slide.

---

## Conventions

**Python ≥3.11, `uv` for dependencies.** Mirror any new dependency into both `pyproject.toml` and `requirements.txt` — the organisers ask for `requirements.txt`.

**Every agent output is a pydantic model in `src/schemas/`.** No bare dicts crossing an agent boundary. Schema validation pass rate is a graded metric; it is only measurable if the schemas exist.

**Every agent call is wrapped in an OTEL span.** Use `src/telemetry/trace.py`; do not call the OTEL SDK directly from agent code. The trace is our demo — an unspanned call is invisible in it.

**Every reasoning loop has a hard cap.** Default 5 iterations, from config, never a magic number in the loop. Log when the cap is hit; loop discipline is graded.

**Secrets in `.env`, loaded once in `src/config.py`.** Never `os.environ` scattered through modules. Never a key in a commit, a log line, or a trace attribute.

**Errors must be actionable.** The organisers explicitly reward this. `"tool call failed"` is not acceptable; `"spark-venue returned 503 after 3 retries; falling back to cached venue list"` is.

**British spelling in user-facing strings** (organise, personalise) — Singapore convention, and it matches the proposal.

---

## Model routing

| Use | Model |
|---|---|
| Local development, iteration, tests | Groq free tier (`langchain-groq`) |
| Match Agent, Continuity Agent — judgement calls | Reasoning tier on Bedrock |
| Onboarding extraction, reflection, briefs | Fast tier |
| The graded evaluation run | Bedrock, so reported token costs are real |

Model choice is config, never hardcoded in an agent. Switching provider must be a one-line change — the lab is built this way and so is this.

---

## Adding an agent

1. Schema in `src/schemas/` first.
2. Module in `src/agents/`, single responsibility, docstring naming which of the organisers' eight agent classes it belongs to.
3. Wire into `src/graph/supervisor.py`.
4. Wrap in a span.
5. Test — at minimum that its output validates and that it respects the loop cap.
6. Update the agent table in `docs/ARCHITECTURE.md`.

---

## Build order

Do not start a milestone before the previous one runs.

| # | Milestone | Done when |
|---|---|---|
| 1 | Skeleton: data model, graph, state machine, OTEL, schemas, loop caps | An empty encounter runs `PROFILED → RELEASED` with a full trace |
| 2 | `spark-overlap`, `spark-profile`, `spark-sim` | 200 personas generated and queryable |
| 3 | Onboarding + Match | Schema pass rate measurable; intent rules unit-tested |
| 4 | Consent gate as `interrupt()` + Trust & Safety | Graph survives a restart mid-consent; every invariant has a test |
| 5 | Encounter Delivery + mock voice bridge | A full encounter completes end to end |
| 6 | Continuity + lock-in | Week-5 behaviour visibly differs from week-1; briefs reference prior calls |
| 7 | Evaluation harness | Three arms produce numbers |
| 8 | AG-UI surface; Guardian, Communication, Date prototypes | Demoable |
| 9 | Recording (≤5 min), deck (≤10 slides), README | Submitted |

**Cut order if behind:** Date → Communication → Guardian.
**Never cut:** the consent gate, Trust & Safety, the evaluation.

Technical Quality is scored 0/1/2 with nothing between *"fully functional"* and *"partially functional"*. Five agents that fully work beat nine that partly do. **When in doubt, cut scope, not quality.**

---

## What not to do

- **Do not add live proximity, live location, or a "someone is nearby right now" trigger.** This was removed deliberately; the reasoning is in `docs/ARCHITECTURE.md` §13.3 and the proposal §3.2. It is a de-anonymisation and stalking vector.
- **Do not add height, appearance, or photo-based filters.** The product's central claim is that it removes judgement-by-photograph.
- **Do not let the Communication Agent invent a shared interest.** Prompts must be grounded in something both people actually said. A hallucinated commonality is a graded fidelity failure and a real user harm.
- **Do not make Guardian Mode imitate a system or OS-level alert.** It is a safety feature, not a deception tool.
- **Do not claim the model predicts attraction.** It estimates who is worth three minutes. The research does not support more (Joel, Eastwick & Finkel, 2017) and neither does our evaluation.
- **Do not use real personal data anywhere.** Everything synthetic, following the lab repo's convention.
- **Do not silently truncate, sample, or cap anything in the evaluation.** If coverage is bounded, log what was dropped.

---

## Evaluation is not optional

Six graded metrics (schema validation, tool-call success, loop discipline, token cost, task completion, answer fidelity) plus four of our own (anonymity leakage, encounter distribution Gini, guardrail false-negative rate, cost per successful connection). Definitions and targets: `docs/ARCHITECTURE.md` §17–18.

**Pre-registered:** if the Match Agent does not beat random assignment on mutual connect rate, we report it. The encounter format would still be the product. Do not tune the evaluation to produce a favourable result — a negative result honestly reported is worth more than a demo that hides one.

---

## Open questions — ask, do not guess

1. Cooldown before two users can be re-matched. **Now measured, not yet decided.**
   `uv run -m eval.sweeps --cooldown 0 7 14 30`: 0d → 980 encounters, **7d → 656
   encounters and the most connections**, 30d → 235. Default left at 30 as
   specified — changing a product parameter because our own simulator preferred
   it would be tuning the evaluation.
2. Lock-in ceiling of 5 — chosen for attention scarcity, not measured. The sweep
   exists but the simulator cannot model attention: simulated people never get
   overwhelmed, so a higher ceiling "winning" there is a limitation, not a finding.
3. Continuity note retention, currently 90 days. Needs justification before any pilot.
4. Voice-channel safety screening is materially harder than text. **Scoped:**
   Trust & Safety screens onboarding intake and post-reveal messages, not audio.
   The call's mitigations are structural — three minutes, anonymous both sides,
   no identity without a mutual yes, either party can end it. Stated in
   `src/safety/trust.py`, `README.md` and ARCHITECTURE §13.8.

### Decided

- **The graded evaluation runs on Bedrock**, so reported token costs are real.
  Dependency installed and routing configured; **not yet run** — no AWS
  credentials on the build machine, so current numbers are Groq/deterministic and
  the report labels them so. `docs/PILOT.md` §4.
- **Interviews remain blocking.** Zero conducted. Pressure-test Q3 fails until at
  least one person in the target group has been spoken to.
- **The pre-registered result is negative and is reported as such.** Spark 12.6%
  vs random 12.6%, p=0.97. How the deck frames it is still open.
