# Spark

**One anonymous three-minute voice call a day, with one person whose path
crossed yours today. Identity is revealed only on mutual consent. The system
then stays with the connection for weeks.**

SimplifyNext Agentic AI Hackathon 2026 · Software AI Track.
Full design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

> Someone living in Singapore who wants to meet people needs a way to reach a
> first real conversation without performing a profile, because the effort and
> superficiality of app-based dating cause most people to give up before they
> ever meet anyone.

Everything in this repository is **simulated**. No real users, no real Singpass
integration (the web onboarding screen is a labelled, data-free concept),
no real telephony, no real location data, no real personal data of any kind. The
voice bridge is a mock. The demo is a recorded simulation run.

---

## Run it

Python ≥ 3.11 and [`uv`](https://docs.astral.sh/uv/). No AWS account and no API
key are needed for anything below.

```bash
cd spark
uv sync                                    # base install, ~15s
cp .env.example .env                       # optional; only needed for the model path

uv run -m src.cli.encounter --seed 42      # ONE encounter, verbose, with its trace
uv run -m src.cli.simulate --weeks 6       # 200 personas, six weeks
uv run -m eval.run_arms                    # Spark vs random vs similarity
uv run -m eval.report                      # the metric tables for the slides

uv run -m src.api                          # the HTTP API on :8000
uv run pytest                              # the whole suite
uv run pytest tests/test_consent.py -v     # the invariants
```

The API drives the **same supervisor graph** as the CLI and the evaluation — the
consent gates reached over HTTP are the same `interrupt()` calls, resumed with
the same `Command(resume=...)`. Routes, and a worked example of all three
outcomes: [`docs/PILOT.md`](../docs/PILOT.md).

**Start with `src.cli.encounter`.** It walks the whole MVP chain — intake,
overlap pool, anonymous encounter, three-minute call, mutual reveal, lock-in —
printing what each person actually saw at each step, the state machine, and the
OpenTelemetry trace underneath.

The onboarding step is worth watching. It reads a transcript containing an
aside about being tall and a sentence that *sounds* like an intent without
naming one, and shows that neither reaches the profile: §13.1 says intent is
never inferred from tone, so the agent asks instead.

Two flags on it are worth running back to back:

```bash
uv run -m src.cli.encounter --seed 42 --decline   # the other person said no
uv run -m src.cli.encounter --seed 42 --timeout   # the other person never answered
```

The two outputs are **byte-identical**, timestamp included. That is invariant 2,
demonstrated rather than asserted.

Other useful entry points:

```bash
uv run -m src.cli.encounter --graph        # print the compiled supervisor graph
uv run -m src.cli.encounter --tools        # the MCP tool catalogue
uv run -m src.cli.encounter --agui         # the AG-UI directives the agent emits
uv run -m src.cli.simulate --write-data    # regenerate data/
uv run -m eval.sweeps --cooldown 0 7 14 30 # what our guessed parameters cost
uv run -m src.mcp.overlap                  # serve one MCP server over stdio
```

### What the model is asked for

A model is asked for a **judgement**, never for bookkeeping. The Match Agent
asks for `MatchChoice { candidate_id, rationale, confidence }` — not for the
date or the user id, which the caller already holds. Same for the Continuity
and Communication agents.

This is not tidiness. Asking a model to reproduce three facts we already know
gives a good answer three extra ways to fail validation, and turns the
schema-validation metric into a measure of our prompt rather than of the model.
Narrowing the schemas moved metric 1 from 37% to 97% on the same model and the
same prompts. The remaining miss was a provider rate limit, and is reported as
one.

### Running with a model

Everything above runs with no API key: the judgement calls fall back to an
explicit deterministic policy, and **every number the system reports is labelled
with the provider that produced it**, so a keyless run is never presented as a
model run.

```bash
echo 'GROQ_API_KEY=gsk_...' >> .env        # free tier, console.groq.com
uv run -m src.cli.simulate --weeks 6       # now uses the model for judgement calls
```

On Groq's free tier the token-per-minute limit is low enough that a long run
will hit it. That is handled rather than hidden: a failed call falls back to the
deterministic policy for that one decision, and after five consecutive failures
a circuit breaker stops calling the provider so the run finishes instead of
paying a timeout on every remaining decision. Both are counted, and
`eval/report.py` prints them under "what this run could not do".

`SPARK_LLM_CALL_BUDGET` bounds how many model calls one run may make. When a run
needs more, the remainder use the deterministic policy and the report says
exactly how many did — CLAUDE.md forbids silently capping anything in the
evaluation.

For Bedrock — **this is where the graded evaluation belongs**, so the reported
token costs are real:

```bash
uv sync --extra aws
echo 'SPARK_LLM_PROVIDER=bedrock' >> .env
echo 'AWS_DEFAULT_REGION=ap-southeast-1' >> .env
# plus credentials: aws sso login --profile <p>, or AWS_ACCESS_KEY_ID/SECRET
```

> ⚠️ **Not yet run.** The dependency is installed and the routing is configured,
> but there are no AWS credentials on the build machine — so every number in the
> current report is Groq-derived or deterministic, and the report says so. See
> [`docs/PILOT.md`](../docs/PILOT.md) §4.

Switching provider is one line, and no agent module mentions Groq or Bedrock —
see [`src/models.py`](src/models.py).

Once a key is present it is used by default. To reproduce the deterministic
baseline on a machine that has one:

```bash
SPARK_LLM_PROVIDER=deterministic uv run -m eval.run_arms
```

The test suite always forces the deterministic provider, so `uv run pytest`
never touches the network and never costs anything, whatever is in `.env`.

---

## The six invariants

These are the product. Each has a test in
[`tests/test_consent.py`](tests/test_consent.py), and most are enforced
*structurally* rather than by remembering to be careful.

| # | Invariant | How it is enforced |
|---|---|---|
| 1 | No identity, photo or number before both parties say yes **after** the call | `RevealView` is the only identity-bearing object, and `safety.consent.build_reveal` is the only function that builds one. A test parses the whole source tree to check nothing else constructs it. |
| 2 | A decline emits **no** observable signal — no count, no timing difference | `build_close_out(encounter_id, viewer_id, call_ended)` is never handed the other party's answer, so it cannot vary with it. A test asserts the signature has not grown. |
| 3 | No distance, place name, coordinate or map position is ever rendered | One function, `safety.guardrails.render`, is the only exit to a user. `AnonymousPeer` has no field for a place. |
| 4 | The call terminates at 180 seconds | Duration is not a parameter of `spark-voice.connect_call`; a test asserts the signature. |
| 5 | Consent events are append-only | `ConsentLedger.record` refuses a second answer; reads hand back copies. |
| 6 | No model decides any of the above | A test parses `src/safety/` and `src/agents/delivery.py` and fails if either imports a model. |

---

## What each file is for

```
src/
  config.py         every setting, loaded once. Secrets read here and nowhere else
  models.py         the ONE model call. Provider routing, budget, fallback
  clock.py          simulated time — nothing calls datetime.now()
  ids.py            pseudonymous handles, drawn from a word list, never from a name

  schemas/          pydantic models. No bare dict crosses an agent boundary
    core.py           the domain: User, Overlap, Encounter, Consent, LockIn
    agents.py         one model per agent output — what metric 1 is measured on
    views.py          the ONLY shapes a user is ever shown

  safety/           the parts a model is not allowed to decide
    consent.py        the append-only ledger and the reveal gate
    guardrails.py     every user-facing string, screened before rendering
    trust.py          Trust & Safety: screening, cooldowns, blocks

  graph/            the supervisor — start here to see the architecture
    supervisor.py     the graph. Its docstring is the architecture slide
    nodes.py          one node per transition; the two gates are interrupt() calls
    state.py          what travels between nodes, and the runtime they share

  agents/           one module per agent, each naming its organiser class
    onboarding.py     Extraction        — intake; never infers intent from tone
    match.py          Decision-Support  — one encounter a day, plus both baselines
    delivery.py       Transaction       — the call and both consent gates
    continuity.py     Personalized      — the "over time" agent
    communication.py  Creative/Gen.     — grounded prompts, opt-in
    date.py           Decision-Support  — concrete proposals, partners labelled
    guardian.py       Embedded          — personal safety, never fakes a system alert

  mcp/              the six MCP servers
    services.py       the tool bodies — what each server may and may not return
    registry.py       the catalogue and the client where metric 2 is measured
    overlap.py profile.py voice.py calendar.py venue.py sim.py

  telemetry/
    trace.py          OTEL setup and the two calls agent code may make
    metrics.py        the six required metrics plus our four

  sim/              the simulator. Nothing in agents/ may import from here
    personas.py       200 synthetic people, and the latent traits nothing can see
    responder.py      what the simulated humans do
    world.py          routines, overlaps, venues
    transcripts.py    what somebody types at intake, messy on purpose
    engine.py         days, then weeks — the engine both the CLI and eval drive

  agui.py           the AG-UI surface — the agent decides what to render

  api/              the HTTP layer the demo client talks to
    app.py            routes; every one a thin wrapper over the graph
    session.py        the live encounter, the graph, the durable checkpoints
    schemas.py        wire shapes, matching web/src/api/types.ts
    mapping.py        internal -> wire, in one place

  cli/
    encounter.py      one encounter, verbose. The demo
    simulate.py       the full run

eval/
  run_arms.py       Spark vs random vs naive interest similarity
  report.py         the metric tables, with the pre-registered result
  sweeps.py         what our guessed parameters actually cost

data/               synthetic personas, the adversarial safety set, the cell registry
tests/              invariants first, then everything else
```

---

## How it works

```
      spark-overlap                     one encounter per person per day
   whose path crossed yours  ─────►  ┌──────────────────────────────────┐
      (coarse cell + bucket,         │  Supervisor — LangGraph          │
       historical only)              │  checkpointed per encounter      │
                                     └────────────┬─────────────────────┘
                                                  │
    pool → select → notify → [ ACCEPT GATE ] → call → [ REVEAL GATE ] → outcome → lock-in
                                   ▲                        ▲
                                   │                        │
                          the graph HALTS here     and here. interrupt().
                          There is no code path past either without a
                          resume carrying BOTH answers.
```

The two gates are `interrupt()` calls, not screens and not flags. The graph
suspends and writes a checkpoint; a later process opens the same checkpoint and
resumes. `tests/test_graph.py::test_the_graph_survives_a_restart_mid_consent`
closes the database, rebuilds the graph from scratch and resumes, because in
production the two answers can be days apart.

**Agent classes.** Spark occupies seven of the organisers' eight classes —
everything but *Information*, since it arranges an encounter rather than
answering questions. `tests/test_schemas.py` checks that claim against the code.

---

## Evaluation

`uv run -m eval.run_arms && uv run -m eval.report`

Three arms — the Match Agent, random assignment, and naive interest similarity —
over the same 200 personas, the same six weeks, and the same eligibility filter.
The arms differ by one field of `SparkRuntime`; a test asserts all three refuse
the same ineligible pair, so the comparison measures selection rather than
filtering.

Each persona carries a **latent affinity** that determines whether two people
actually enjoy three minutes together, and which nothing in the agent layer can
observe. Their stated interests are noisy indicators of it. This is deliberate:
Joel, Eastwick & Finkel (2017) found that machine learning over 100+
self-reported traits could not predict relationship-specific attraction above
chance, and a simulator without a large irreducible term would be modelling a
world where that result is false.

Two tests keep that honest in both directions. `test_nothing_outside_the_simulator_reads_a_latent_trait`
fails if any agent, arm or metric touches the answer sheet. And
`test_stated_interests_carry_a_weak_but_real_signal` fails if the correlation
between shared interests and latent affinity leaves the band (0.01, 0.25) — at
zero the matcher could not beat chance however good it was, and a
pre-registered comparison that can only come out one way is not a test.

**Pre-registered, before any of it was run:** if the Match Agent does not beat
random assignment on mutual connect rate, we report it. `eval/report.py` prints
whichever answer the numbers give, with a two-proportion z-test, and says
plainly when a difference is not distinguishable from noise — including when
the sample is too small to test at all.

We do not claim the model predicts attraction. It estimates who is worth three
minutes.

---

## Known limits, and what we are not claiming

Stated here rather than discovered by a judge.

- **No interviews have been conducted.** The architecture's own pressure test
  (§3, Q3) fails until we have spoken to at least one person in the target
  group. Everything downstream rests on an unverified problem statement.
- **Trust & Safety screens text, not audio.** Onboarding intake and post-reveal
  messages are screened. The call itself is not. Voice-channel screening is
  materially harder, and the mitigations for the call are structural instead:
  three minutes, anonymous on both sides, no identity without a mutual yes,
  either party can end it. This is scoped deliberately, not overlooked.
- **The cooldown is the binding constraint on encounter supply, and it is a
  guess.** `uv run -m eval.sweeps --cooldown 0 7 14 30` shows what each value
  costs. Overlap is driven by routine, so a person's pool is largely the same
  faces each day and a long cooldown exhausts it. The default is left at the
  specified 30 days: changing a product parameter because our own simulation
  preferred it would be tuning the evaluation.
- **The lock-in ceiling of five** was chosen for attention scarcity, which this
  simulator does not model — simulated people never get overwhelmed. Treat a
  higher ceiling looking better in a sweep as a limitation of the simulator.
- **Continuity note retention is 90 days** and that number needs a real
  justification before any pilot.
- **The voice bridge is a mock**, and injects a small deterministic failure rate
  so the tool-call success metric measures something real. A run in which it
  never fails has not tested the fallback.
- **Simulated humans are a model, not evidence.** The response coefficients in
  `src/sim/responder.py` are stated priors, set before any arm was run and
  applied identically to all three. They are not measurements.

---

## Conventions

- Python ≥ 3.11, `uv`. Dependencies are mirrored into `requirements.txt`.
- Every agent output is a pydantic model in `src/schemas/`.
- Every agent call is wrapped in an OTEL span, via `src/telemetry/trace.py`.
- Every reasoning loop has a hard cap, from config, via `bounded_loop`.
- Secrets in `.env`, read once in `src/config.py`. `.env` is gitignored, and no
  key reaches a log line or a span attribute.
- Errors name what failed, what was tried, and what happens next.
- British spelling in user-facing strings.

Everything is synthetic. There is no real personal data in this repository, and
there are no credentials in it.
