# Spark — Architecture & Submission Specification

**SimplifyNext Agentic AI Hackathon 2026 · Software AI Track**
Companion to *Spark — Solution Proposal (v2)*.
Submission 7 Sep 2026 · Semi-finals 9–11 Sep · Grand finale 18 Sep.

> **What Spark is.** One anonymous three-minute voice call a day, with one person whose path crossed yours today. Identity is revealed only on mutual consent. The system then stays with the connection for weeks.

---

# Part I — What the organisers asked for

Recorded verbatim from the briefing so the build can be checked against it rather than against memory.

## 1. The problem statement we are answering

> **Design for a World in Transformation**
>
> Change is everywhere — in how we live, learn, and relate to one another. Transformation takes time, effort, and the right support at the right moment.
>
> This is your chance to build something that helps. We envision a solution that **plans, acts, and adapts over time**.
>
> Your team will choose the problem and decide who it serves. You will design a solution that **thinks ahead, takes action, and leaves people genuinely better off**.

Three obligations follow, and each maps to something we must be able to point at:

| Obligation | Where Spark satisfies it |
|---|---|
| Plans, acts and adapts **over time** | The Continuity Agent and the lock-in layer — weeks, not one transaction |
| **Thinks ahead** | Daily encounter selection under uncertainty; proposing meetings before being asked |
| **Takes action** | Acts unprompted: selects, notifies, connects the call, proposes, nudges |
| Leaves people **genuinely better off** | Outcome metrics in §12.3, not engagement metrics |

## 2. Design thinking and the POV format

Stages: **Empathise → Ideate → Define → Prototype → Test**, revisited as we learn.

Required problem-statement format:

```
[User] needs [a way to ...] because [insight].
```

Their worked example: *"A caregiver needs a reliable way to track daily medication because missed doses lead to avoidable hospital visits."*

- ✓ Names a real user, a real need, and the evidence
- ✗ Names a tool, a feature, or a technology

**Our POV statement:**

> Someone living in Singapore who wants to meet people needs a way to reach a first real conversation without performing a profile, because the effort and superficiality of app-based dating cause most people to give up before they ever meet anyone.

## 3. The pressure test — five questions, any "no" sends us back to Empathise

| # | Question | Their standard | Our status |
|---|---|---|---|
| 1 | Can we name one person? | A role at a moment, specific enough to picture them walking into the room. "Users" and "people" will not pass | **Pass** — a 28-year-old in the CBD with three apps installed, matches unanswered, no first date in seven months, who has not deleted the apps but has stopped opening them |
| 2 | Can we cite the evidence? | A figure, a source, and a date. If the only support is that it feels true, we have an assumption to test | **Pass** — MPS 2021 (58% / 57%, n=5,865); Lunch Actually Paktor 2024 (88% / 36% / 21%, n=350) |
| 3 | Would that person recognise themselves? | We have spoken with at least one of them. A statement written entirely from our own imagination ends up describing the team | **OPEN — the one gap.** Zero interviews conducted. Must be closed before submission |
| 4 | Does it survive a different solution? | The statement should still hold if another team builds something completely unlike ours. **The sharpest question** | **Pass** — our statement names no app, no agent, no call. A matchmaking service or a physical club would answer it too |
| 5 | *(fifth question not captured on the slide)* | — | — |

> **Q3 is the live risk.** Their own warning is that an imagined statement ends up describing the team. Five conversations with people who deleted a dating app in the last six months closes it. One real quote on slide 2 is worth more than any statistic on it.

## 4. Digital AI agent classes

The organisers' taxonomy. Agents may belong to several classes.

| Class | Definition | Spark agents in this class |
|---|---|---|
| **Information** — Answer & Advise | Retrieve, summarise or explain | — |
| **Extraction** — Parse & Transform | Convert unstructured content into structured, actionable data | Onboarding |
| **Transaction** — Do & Automate | Perform tasks on behalf of the user by integrating with systems | Encounter Delivery, Date, Itinerary |
| **Decision-Support** — Guide & Recommend | Help with choices by analysing data and recommending actions | Match, Date |
| **Creative / Generative** — Create & Draft | Produce new content based on user intent | Communication |
| **Orchestration** — Coordinate & Integrate | Combine multiple systems and flows as a control tower | Supervisor |
| **Personalized** — Adapt & Learn | Customise from semantic and episodic context | Continuity |
| **Embedded** — Live Where People Work | Exist inside other apps or processes rather than as standalone chatbots | Guardian, Trust & Safety |

Spark occupies **seven of the eight classes**. This belongs on the technical architecture slide — naming their taxonomy back at them is free credit on Technical Quality.

## 5. Development best practices required

- **Code readability** — clean, commented code; clear variable names; consistent formatting. Organise code so that it *showcases the application of Agentic AI techniques*.
- **Project folder structure** — a logical hierarchy: `src/`, `docs/`, `data/`, `tests/`.
- **Documentation** — concise and clean. A good `README.md` is sufficient for judges.
- **Error handling** — baseline: functional resilience. Going further: *make errors actionable for business users.*

## 6. The six performance metrics they named

| # | Metric | Their guiding question |
|---|---|---|
| 1 | Schema Validation Pass Rate — share of outputs that parse and validate on the first attempt | "Is the output usable by another system?" |
| 2 | Tool-Call Success Rate — share of tool calls returning a usable result; log the failures | "Does the agent reach for the right hands?" |
| 3 | Loop Discipline — iterations per task against the cap, and how often a run hits the cap | "Is it converging or circling?" |
| 4 | Token Cost Per Run — input, output, cache read and cache creation across a whole run | "What does one answer actually cost?" |
| 5 | Task Completion Rate — requests resolved end to end without a human stepping in | "Did it carry the job to the end?" |
| 6 | Answer Fidelity — scored against a reviewed ground-truth set, using a rubric or an LLM judge | "Is it right, as well as plausible?" |

Instrumented in §12.1. Four further metrics specific to this product are in §12.2.

## 7. Deliverables

| Deliverable | Constraint |
|---|---|
| Project files / workflow | Max 5 GB. **One submission only** |
| Presentation deck | **Max 10 slides** |
| Digital solution video **or** video recording of simulation | **Max 5 minutes** |

The deliverables must:

1. **Answer the question** — clearly explain the problem and the innovative solution
2. **Showcase knowledge of Agentic AI** — technical soundness and functionality
3. **Create business impact** — demonstrate that the solution addresses the problem statement

> We take the **simulation recording** option. It lets us show six weeks of adaptation inside five minutes, which a live walkthrough cannot, and it removes the risk of a live voice bridge failing on camera.

## 8. Project file requirements

Build a simple **proof-of-concept** demonstrating the Agentic AI component.

- **README** covering (a) instructions to run the code, (b) an overview of the code and the purpose of each script/file
- **Environment** — virtual environment with `requirements.txt` (Docker also acceptable); path variables; secrets and keys in `.env`
- **Language** — **Python strongly recommended**
- **Execution** — no extensive test data required. They will look at: whether the solution runs as demonstrated in the video; whether the presentation methodology is reflected at code level (in-line documentation helps); and testing/evaluation covered in the slides

## 9. Judging criteria — five criteria, 20% each, scored 0/1/2

| Criterion | 2 points | 1 point | 0 points |
|---|---|---|---|
| **Benefits delivered** — what positive impact does it bring to users, the organisation or the community? Benefits may include revenue, productivity, quality, compliance, **or quality of life** | Clear benefits; scalable or easily adopted | Clear benefits | No or limited benefits |
| **Original / Innovative** — how original and creative is this solution? | Unique and innovative approach | Based on existing ideas but addresses the problem | Not unique; existing solutions address it effectively |
| **Effectiveness** — how effective is it in addressing the problem? | Fully addresses and resolves the problem | Partially addresses, not fully resolved | Minimal effectiveness |
| **Technical quality** — is the prototype functional and technically sound? | Technically advanced, fully functional prototype with minimal work needed for production | Functional prototype with minor work needed | Partially functional, or does not meet core requirements |
| **Presentation** — how effectively does the team articulate the problem and explain how the solution tackles it? | Clearly explained the problem and demonstrated the benefits | Partially explained, with prompting or clarification needed | Unable to clearly explain |

Their guidance on where each is evidenced:

- Benefits → **link features to measurable improvements**
- Original → **point out what makes the approach different from existing solutions**
- Effectiveness → **use evidence — data, tests, scenarios — to prove it works**
- Technical quality → **show a functional prototype and explain how it is robust**
- Presentation → **structure the story well, rehearse delivery**

> **Scope consequence.** Technical Quality has no partial credit between "fully functional" and "partially functional". Six agents that fully work beat nine that partly do. The cut list in §14 exists for this reason.

## 10. Required deck structure (max 10 slides)

| # | Slide | Our content |
|---|---|---|
| 1 | Title & Team | Names, roles, one-line mission |
| 2 | Problem Statement / Why It Matters | POV statement, MPS 2021 and Paktor 2024 figures, one real interview quote |
| 3 | Solution Overview | Crossed paths → three-minute anonymous call → mutual reveal → lock-in |
| 4 | Methodology | The agentic loop; consent as an interrupt; why overlap replaced live proximity |
| 5 | Technical Architecture | Supervisor graph, MCP tools, AgentCore, seven of eight agent classes |
| 6 | Innovation & Uniqueness | Voice before appearance; coincidence as selection; the system stays past the match |
| 7 | Benefits Delivered | Outcome metrics vs baseline arms; cost per successful connection |
| 8 | Demo Preview | Simulation stills plus the OpenTelemetry trace of one encounter |
| 9 | Roadmap & Future Potential | MVP → pilot → platonic/professional modes and partnerships |
| 10 | Conclusion & Call to Action | — |

---

# Part II — Architecture

## 11. Design principles

1. **The unit of state is the Encounter, and then the Lock-in** — not the User. Both are long-lived checkpointed threads; a lock-in spans weeks.
2. **Deterministic where it must be auditable, model-driven where judgement is required.** The consent gate, eligibility rules and identity-reveal logic are ordinary code with tests. A model must never be the only thing standing between a stranger and someone's identity.
3. **Every external capability is an MCP server.** No direct SDK calls from agent code — this is what lets the same graph run against the simulator and against live services.
4. **Consent is an interrupt, not a screen.** The graph halts. There is no code path that proceeds without both approvals.
5. **Location is never live.** Coarse cell + time bucket, historical only. No distance is ever stated to a user.
6. **Every encounter and every continuity action emits a trace.** The trace is the debugging tool, the explainability source, and the demo.

## 12. System overview

```
                        ┌───────────────────────────┐
                        │  Supervisor (LangGraph)   │
                        │  checkpointed per thread  │
                        └─────────────┬─────────────┘
                                      │
   ┌──────────┬───────────┬───────────┼───────────┬───────────┬──────────┐
   ▼          ▼           ▼           ▼           ▼           ▼          ▼
Onboarding  Match   Encounter  Continuity  Communication  Date   Itinerary  Guardian
 (Extract) (Decision) Delivery  (Personal-  (Generative)   (Dec.  (Transac-  (Embedded)
            Support) (Transac-    ized)                   Support)  tion)
                       tion)
                                      │
                            Trust & Safety (cross-cutting)
                                      │
                                     MCP
    ┌──────────┬──────────┬──────┴───┬──────────┬──────────┬──────────┐
    ▼          ▼          ▼          ▼          ▼          ▼          ▼
spark-overlap spark-profile spark-voice spark-calendar spark-venue spark-sim spark-places
 (coarse cell  (AgentCore   (anonymous  (availability) (date       (personas,  (real venues,
  + time)       Memory)      bridge)                    options)    eval arms)  OpenStreetMap)
```

`spark-places` is the only server that returns a coordinate, and the only one
that is never told who is asking — see §13.9.

## 13. Agent specifications

### 13.1 Onboarding — `LLM` · *Extraction*

Conversational intake, not a form. Emits `Profile` + `ConsentScope`.

Extracts `intents[]` (partner long-term / partner short-term / friends), `interests[]`, `personality`, `lifestyle`, `languages[]`, `availability_window`, `verification_tier`, `dealbreakers[]`, and the explicit list of fields permitted for matching.

**Excluded by design:** height and appearance filters. A product whose central claim is removing judgement-by-photograph cannot filter on physical attributes.

**Rule:** intent is never inferred from tone. If the user did not name it, it is not set.

### 13.2 Match — `LLM + SEARCH` · *Decision-Support*

Selects **one** encounter per day from that day's overlap pool.

Inputs: overlap pool, both profiles, prior feedback, cooldowns, blocklist.
Output: `MatchDecision { candidate_id, rationale, confidence }` — schema-validated.

Objective order: intent compatibility (hard) → availability → language → estimated compatibility → novelty against recent encounters → **distribution fairness** (see §15.2).

**The claim we make and defend:** the model estimates compatibility from stated preferences, interests, personality and behavioural feedback in order to choose who is worth three minutes. It does not predict attraction. Joel, Eastwick & Finkel (2017) showed that ML over 100+ self-reported traits cannot predict relationship-specific attraction above chance, so we do not claim it — and we benchmark against random assignment in §15.3.

### 13.3 Encounter Delivery — `DETERMINISTIC` · *Transaction*

Owns notification → dual accept → voice bridge connect → hard three-minute stop → private post-call prompt → reveal or silent close.

Five enforced invariants:

1. No identity, photo or number is exposed before both parties say yes post-call.
2. A decline emits **no** observable signal to the other party — no count, no delay, nothing.
3. No distance, place name or map position is ever rendered to a user.
4. The call terminates at 180 seconds regardless of state.
5. Every consent event is written to an append-only ledger that is never joined into anything user-visible.

Implemented as a LangGraph `interrupt()`: state checkpoints, resumes on both approvals, times out to `abandoned`.

### 13.4 Continuity — `LLM` · *Personalized* — **the "over time" agent**

Owns up to ten active lock-ins per user across weeks.

- Retains what the pair actually discussed; surfaces it before the next contact
- Detects a lock-in going quiet and offers a concrete re-entry rather than a generic nudge
- Proposes a specific time and place from both calendars and interest sets
- Learns each user's preferred pace and adjusts
- Releases a dead lock-in gracefully, freeing the slot without confrontation

This agent is what makes the "plans, acts and adapts over time" claim true. Notes are stored in AgentCore Memory, scoped per user, deletable on request, and never surfaced to anyone the note was not about.

### 13.5 Communication — `LLM` · *Creative/Generative* · opt-in

Detects a stalling conversation and offers a prompt **grounded in something both people actually said**. Suggests; never speaks for the user. A hallucinated shared interest is a fidelity failure and is measured as one (§12.1, metric 6).

### 13.6 Date — `DETERMINISTIC` · *Decision-Support / Transaction*

Proposes **three date paths** — a thing to do, and somewhere to eat or sit afterwards — from interests both people stated, once a pair has decided to meet. Ranked on fit first; commercial partners may only appear where they already rank, and are labelled beside the venue rather than in fine print.

Three rather than one because "we should meet sometime" is where most of these connections quietly die, and a single venue is only slightly easier to accept than nothing. The three must differ in their lead activity, so the pair choose the shape of an evening rather than between synonyms.

**Deterministic, not `LLM`.** Ranking venues by tag overlap and pairing an activity with somewhere to eat is a lookup and an ordering, not a judgement — and a suggestion that varies run to run cannot be filmed twice. The judgement of *whether* to propose was already made by the Continuity Agent.

**How this coexists with invariant 3.** A date plan points somewhere, and invariant 3 forbids rendering a place. The two are reconciled by *when* and by *what*:

- **When** — planning runs on a `LockIn`, which exists only after a mutual reveal. Two people who have exchanged names and are choosing where to meet are picking a destination together; that is not a disclosure of where either of them was. Enforced on both sides: `GET /api/encounters/{id}/dates` returns `409` before a mutual yes, and the `/dates` screen redirects without one.
- **What** — `suggest_venues` is never given a cell, a coordinate, a distance, or either person's overlap history. It ranks on shared interests and time of day alone. There is no location field on a venue record or on `DateStop`, so "near where you both were" cannot be assembled. `tests/test_date.py` asserts both structurally, against the function signature and the record keys, because this is the one feature where that inference could arrive legitimately-looking.

Venues at this stage are **kinds of place** — "a hawker centre, one dish each and swap" — never named businesses. `DateStop` has no field for a name, an address or a coordinate, so the ranking cannot see one.

Naming a real place is a **separate step, by a separate agent**, and only after this one has decided the shape of the evening. See §13.9. The split is what keeps the reconciliation above true: the half that ranks cannot read a location, and the half that reads locations does no ranking about people.

A path that cannot cite an interest **both** people listed is not built, for the same reason the Communication Agent may not invent a shared interest. When there is nothing to work with the agent returns an empty plan and says why, so a short list reads as a fact about the pair rather than as a failure.

#### Date Studio

The planner around that agent, and the product's answer to "why come back". The loop is: choose a connection → set constraints from fixed boxes → receive three grounded plans → save, reject with a reason, or refine → inspect and correct what Spark learned → better plans next time.

**It remembers, and it does not train.** Preferences, plan snapshots and feedback are rows in SQLite (`src/memory/date_memory.py`), in the same database as the graph checkpoints so the memory and the encounters it is about are deleted together. Improvement is deterministic re-ranking over those rows — **nothing here updates a model's weights**, and no interface copy may imply it does. AgentCore Memory is the intended replacement for the store; it is a **target, not a live integration**, and nothing in this repository talks to it.

**Memory has two scopes.** `user` items are true of a person across connections; `lockin` items apply to one pair only and must never influence another, because a reaction to one person is not a fact about them in general. Every item records whether it was chosen (`explicit`, confidence 1.0) or inferred from behaviour (`feedback`, capped at 0.6 and moved in steps), so an inference can never outrank something someone actually said and a single rejection is a nudge rather than a permanent dislike.

**Remembering is opt-in.** A constraint set for tonight is context, not a preference. It is stored only when the person ticks *Remember this*, because a system that promotes tonight's mood into a durable belief will be wrong about someone forever without ever having been told anything untrue.

**The scorer explains itself from its own terms.** `src/agents/date_scoring.py` records every term that moved the number, and the rationale is assembled from that record — so a plan cannot describe a reason the ranking did not use. Ranking happens before commercial-partner metadata is attached, unchanged from §13.6.

**Ethical retention.** Saved plans, better recommendations and a memory-control surface. Deliberately absent: streaks, swipe feeds, manufactured urgency, "they are waiting for you", compatibility percentages, and any question about whether a date went well — Spark grades the recommendation, never the relationship. The intended metric is weekly meaningful planning actions per active lock-in, not session length.

**Phase 2 (collaborative proposals) is designed, not built.** It needs two authenticated viewers, and there is no auth.

### 13.7 Guardian — `DETERMINISTIC` · *Embedded*

A discreet in-app action triggers a preconfigured interruption giving the user a natural reason to leave, followed by a private check-in. Paired with an optional trusted-contact plan, a timed check-in after any first in-person meeting, and an incident log.

**Never imitates a system-level or OS alert.** Positioned and built as a personal safety feature, not a deception tool.

**A concern closes the encounter, on the server.** Answering the private check-in with "something felt off" writes a durable closure against that encounter, and `SparkSession.reveal_allowed` — the single boundary `POST /consent`, the lock-in store and `GET /dates` all consult — refuses from then on. No identity is exchanged, no lock-in opens, date planning is unavailable, and the closure survives a new process against the same checkpoint database.

Three things it deliberately does not do. It does not resume the graph, because that would mean supplying an answer the other party never gave, and a fabricated consent record is not safer than an unanswered gate. It does not revise any append-only consent record (invariant 5). And it tells the other party nothing: the consent payload is byte-identical to an ordinary decline, so from their side this is a decline or a no-show, indistinguishable as invariant 2 requires.

The closure is written **before** the person is told anything, so the endpoint cannot claim an encounter is closed that is not. It is idempotent, so a repeated submission cannot weaken it.

### 13.8 Trust & Safety — `DETERMINISTIC + GUARDRAILS` · cross-cutting

Screens onboarding text and post-reveal messages for harassment, sexual content, scam patterns, and attempts to route around the consent gate. Enforces cooldowns, blocks and reports. All generated user-facing strings pass Bedrock Guardrails before rendering; failures are logged, never silently dropped.

### 13.9 Itinerary — `DETERMINISTIC` · *Transaction*

Turns one ranked `DatePath` into a plan two people can follow: **named venues, addresses, clock times, walking legs between the stops, a cost estimate and a reason for each choice**. One coherent evening, not a list of suggestions somebody has to assemble.

**Why it is a separate agent from Date.** Because only one of the two is allowed near a coordinate. The Date Agent *ranks*, from shared interests and remembered preferences, over a catalogue with no location field. This agent *binds*, from a catalogue that has coordinates and has never been told where either person is or has been. Keeping them apart makes "near where you both were" **unbuildable rather than merely unbuilt**: there is no call site anywhere holding both an overlap cell and a venue coordinate.

**Where the venues come from.** OpenStreetMap, fetched once by `scripts/fetch_venues.py` and committed. Never a live call — a demo that queries a public API on stage fails when the wifi does, and a plan that changes between takes cannot be filmed twice.

These are **real businesses that Spark has not visited or evaluated**, and nothing in the product implies otherwise. There is no field anywhere for a rating, a review count or a "recommended" flag. Attribution — "© OpenStreetMap contributors" — is rendered wherever venues appear, which is a licence condition rather than a courtesy.

**What it refuses to do.**

- **Invent a venue.** With no data loaded it returns a typed refusal with a reason and the interface shows an unavailable state. A fabricated address is a real person standing outside a building that was never there.
- **Send anybody to a closed venue.** Opening hours are checked at the stop's actual arrival time and a closed venue is skipped, not annotated. `ItineraryStop` refuses to validate one, so no code path can render it.
- **Assume a venue is open.** Missing hours are a third state, `unknown`, rendered as unknown. OpenStreetMap's coverage is patchy and treating "no data" as "open" is how a plan sends two people to a locked door.
- **Claim an interest a venue does not serve.** Interests are keyed per OSM tag in `src/mcp/venue_rules.py`. An earlier mapping keyed them by coarse category and gave a 24-hour gym `chess`, which would have produced "you have both mentioned chess" beside a gym — the same invented commonality the Communication Agent is forbidden.
- **Carry contributed free text into the product.** `opening_hours` is user-contributed and one real fetch returned a contributor's name and mobile number in it. The field is *whitelisted* to recognisable syntax, not scrubbed; anything else becomes "hours unknown".

**Stops are ordered by proximity to the previous stop.** Ranked on fit alone the planner produced a gallery and a coffee shop ten kilometres and two hours apart in one evening — both individually well chosen, the plan nonsense. This is venue-to-venue distance between stops *already selected*; nothing here knows where a participant is, and `spark-places` cannot be told.

**Maps without a key.** The route is drawn from the coordinates rather than tiled, so it works offline like the rest of the client and there is no browser API key to leak. Per-stop **Navigate** buttons open real Google Maps directions via `maps/dir/?api=1`, a documented public URL that takes no credential.

**After the date**, `DateReflection` records how it went — privately. There is no route returning another person's reflection, no field saying whether they wrote one, and no status meaning "they turned you down". A plan the other person did not take up is `cancelled`, indistinguishable from one nobody got round to: invariant 2's rule, still holding long after the reveal.

## 14. State machine

```
 PROFILED ─► POOLED ─► SELECTED ─► NOTIFIED ─► PENDING_ACCEPT ─► CONNECTED
                                                     │                │
                                          (decline / timeout)         ▼
                                                     ▼            CALL_ENDED
                                                 ABANDONED            │
                                                                      ▼
                                                              PENDING_CONSENT
                                                                 │        │
                                                        (mutual) │        │ (not mutual)
                                                                 ▼        ▼
                                                            REVEALED   CLOSED
                                                                 │
                                                                 ▼
                                                            LOCKED_IN ──► (weeks) ──► RELEASED
```

`ABANDONED` and `CLOSED` are normal terminal states, not errors, and must produce no observable signal to the other party.

> **Amendment, found during implementation.** The diagram above draws only `CONNECTED → CALL_ENDED`, which leaves nowhere to go when both parties have accepted and the voice bridge then fails. `src/schemas/core.py` therefore also permits `CONNECTED → ABANDONED`. `ABANDONED` is the honest terminal — the call did not happen — and it is the safe one, because it is silent: an outage on our side must not be distinguishable from a decline on theirs. Anything else would leak "the other person was willing" through an error message. The state machine refused the transition until it was declared, which is what the machine is for.

## 15. Data model

```
User          id, profile, consent_scope, verification_tier, blocklist[], lockin_slots(≤10)
Overlap       user_a, user_b, cell_id, time_bucket, date        # coarse, historical only
MatchDecision date, user_id, candidate_id, rationale, confidence
Encounter     match_id, state, accepted[], call_started, call_ended, trace_id
Consent       encounter_id, user_id, decision, timestamp        # append-only
LockIn        pair_id, opened_at, last_contact, pace_pref, state
Continuity    lockin_id, note, source, expires_at
Outcome       encounter_id | lockin_id, private_signals[], prediction_error
```

## 16. Technology mapping

| Layer | Choice | Why |
|---|---|---|
| Orchestration | **LangGraph** | Durable checkpointed threads spanning weeks; `interrupt()` *is* the consent gate; supervisor pattern |
| Runtime | **Bedrock AgentCore Runtime** | Serverless agent hosting |
| Memory | **AgentCore Memory** | Long-term profile and continuity notes, separate from per-encounter state |
| Tool bridge | **AgentCore Gateway** | Wraps REST services as MCP tools |
| Tools | **MCP**: `spark-overlap`, `spark-profile`, `spark-voice`, `spark-calendar`, `spark-venue`, `spark-sim`, `spark-places` | Same graph runs against simulator and live services by swapping endpoints |
| Client | **AG-UI** | The agent decides what to render — encounter card, consent prompt, brief |
| Observability | **OpenTelemetry** | One trace per encounter and per continuity action |
| Safety | **Bedrock Guardrails** | Every generated user-facing string |
| Language | **Python** | Strongly recommended by the organisers |

---

# Part III — Evaluation

## 17. Instrumenting the six required metrics

| # | Metric | Applied to Spark | Target |
|---|---|---|---|
| 1 | Schema validation pass rate | `MatchDecision`, `DatePlan`, `ContinuityAction` parse on first attempt | ≥ 98% |
| 2 | Tool-call success rate | Overlap, profile, voice bridge, calendar, venue. **The voice bridge is the riskiest call and the one most likely to fail on camera** | ≥ 95% |
| 3 | Loop discipline | Reasoning iterations per encounter decision against a hard cap of 5; share of runs reaching cap | < 2% at cap |
| 4 | Token cost per run | Cost of one daily encounter decision and one continuity action. **× DAU this is our unit economics, not trivia** | Reported |
| 5 | Task completion rate | Selection → notify → both respond → connect → outcome recorded, no manual intervention. **Completion means *reaching* the human gate, not passing it** — otherwise the metric punishes users for behaving normally | ≥ 90% |
| 6 | Answer fidelity | Communication Agent prompts scored by rubric + LLM judge with human spot-check: is the prompt grounded in something both people actually said? | ≥ 95% |

> Loop caps, output schemas and OTEL spans must exist from day one. All three are trivial to add at the start and painful to retrofit in week two.

## 18. Four metrics specific to this product

The six above do not measure what would actually sink Spark.

| Metric | Definition | Why it exists |
|---|---|---|
| **Anonymity leakage rate** | Share of simulated encounters in which a participant could identify the other before mutual reveal. **Target: zero** | This is what *proves* the move from live proximity to path overlap rather than asserting it. Lead with it when safety is questioned |
| **Encounter distribution (Gini)** | Concentration of encounters across users | If a small minority receive most encounters, we have rebuilt the platform we set out to replace. Measured, and it constrains the Match Agent |
| **Guardrail false-negative rate** | Harmful content passing screening, against a seeded adversarial set | False negatives matter enormously more than false positives here |
| **Cost per successful connection** | Token + infra cost ÷ mutual connections produced | The number that decides whether the business works |

## 19. Does the matching add anything, and are people better off

~200 synthetic personas, six simulated weeks, three arms: **Spark Match Agent**, **random assignment**, **naive interest-similarity**. Each persona carries a latent affinity the system cannot observe.

| Metric | Definition | Level |
|---|---|---|
| Encounter accept rate | Notifications accepted by both parties | Matching |
| Mutual connect rate | Calls ending in yes from both sides | Matching |
| Lock-in conversion | Connections becoming an active lock-in | Outcome |
| Met in person by day 14 | Lock-ins reaching a real meeting | Outcome |
| Lock-in survival at week 4 | Lock-ins still active after four weeks | **North star** |

**Pre-registered:** if the Match Agent does not beat random assignment on mutual connect rate, we report it. The encounter format would still be the product, and a negative result honestly reported is worth more than a demo that hides one.

---

# Part IV — Delivery

## 20. Repository structure

```
spark/
├── README.md              # run instructions + purpose of every script (required)
├── requirements.txt       # or Dockerfile
├── .env.example           # never commit real keys
├── src/
│   ├── graph/             # LangGraph supervisor, nodes, state machine
│   ├── agents/            # one module per agent, in-line documented
│   ├── mcp/               # the six MCP servers
│   ├── schemas/           # pydantic models — the schema-validation metric depends on these
│   └── telemetry/         # OTEL setup, metric collectors
├── data/                  # synthetic personas, adversarial safety set
├── tests/
│   ├── test_consent.py    # invariants: no reveal without dual yes, decline is silent
│   ├── test_intent.py     # eligibility rules
│   └── test_schemas.py
├── docs/
│   ├── ARCHITECTURE.md    # this file
│   └── PROPOSAL.docx
└── eval/
    ├── run_arms.py        # Spark vs random vs similarity
    └── report.py          # emits the metric tables for the slides
```

Code should be organised so it visibly *showcases the Agentic AI techniques* — the organisers say this explicitly, so the supervisor graph, the interrupt, and the tool definitions should be easy to find and commented.

## 21. Build scope, 24 Aug → 7 Sep

| Days | Deliverable | Done when |
|---|---|---|
| 1–2 | Data model, LangGraph skeleton, state machine, OTEL, schemas, loop caps | An empty encounter runs PROFILED→RELEASED with a full trace |
| 2–3 | `spark-overlap`, `spark-profile`, `spark-sim` | 200 personas generated and queryable |
| 3–4 | Onboarding + Match agents | Schema pass rate measurable; intent rules unit-tested |
| 5–6 | Consent gate as `interrupt()` + Trust & Safety | Graph survives a restart mid-consent; every invariant in §13.3 has a failing-if-broken test |
| 6–8 | Encounter Delivery + mock voice bridge | A full encounter completes end to end |
| 8–10 | Continuity + lock-in layer | Week-5 behaviour visibly differs from week-1; briefs reference prior calls |
| 10–11 | Evaluation harness, three arms | Numbers in hand |
| 11–12 | AG-UI surface; Guardian, Communication, Date prototypes | Demoable |
| 12–13 | Simulation recording (≤5 min), deck (≤10 slides) | Cut and rehearsed |
| 13–14 | README, requirements, buffer | One submission, first time |

**Cut order:** Date → Communication → Guardian.
**Never cut:** the consent gate, Trust & Safety, the evaluation.

## 22. Traceability — every criterion to an artefact

| Criterion (20%) | Evidence | Where |
|---|---|---|
| Benefits delivered | Outcome metrics vs baseline; cost per successful connection; "quality of life" named in their own rubric language | Slide 7, §18–19 |
| Original / Innovative | Voice before appearance; coincidence as selection; the system stays past the match; comparison table | Slide 6, proposal §9 |
| Effectiveness | Three-arm simulation with pre-registered falsification | Slide 7, §19 |
| Technical quality | Six metrics + four product metrics; test suite on invariants; seven of eight agent classes; robustness via §11 principles | Slide 5, §17–18, `tests/` |
| Presentation | Ten slides in their required order; rehearsed; one real interview quote on slide 2 | Deck |

## 22a. Implementation notes

Written during the build, against the specification above.

**Agent table (§13), as built.** Seven of the eight agent classes, each declared in
its module's `AGENT_CLASS` constant and checked by `tests/test_schemas.py`:

| Module | Organisers' class | Model or deterministic |
|---|---|---|
| `src/agents/onboarding.py` | Extraction | LLM, with a deterministic fallback |
| `src/agents/match.py` | Decision-Support | LLM over a deterministic shortlist |
| `src/agents/delivery.py` | Transaction | **Deterministic** — no model imported |
| `src/agents/continuity.py` | Personalized | LLM, rules decide *which* action |
| `src/agents/communication.py` | Creative/Generative | LLM, grounding verified in code |
| `src/agents/date.py` | Decision-Support / Transaction | Deterministic over a tool result |
| `src/agents/guardian.py` | Embedded | **Deterministic** |
| `src/safety/trust.py` | Embedded (cross-cutting) | **Deterministic + guardrails** |
| `src/graph/supervisor.py` | Orchestration | The graph itself |

*Information* is absent, and deliberately so: Spark arranges an encounter rather
than answering questions. Claiming the eighth class would be the kind of
overstatement the evaluation exists to catch.

**The MCP transport.** The six servers in `src/mcp/` are real: each builds an
`MCPServer` and serves over stdio (`uv run -m src.mcp.overlap`), and
`tests/test_mcp.py` lists their tools over the protocol. The simulation calls
the same function bodies in-process, because a six-week run over 200 personas
makes ~13,000 tool calls and six subprocesses per call would make the
evaluation impossible. The boundary — and therefore the claim in §16 that the
same graph runs against the simulator or against live services — is the
interface, not the transport.

**Model routing, in practice.** A six-week simulation asks for thousands of
judgement calls. `src/models.py` holds a per-run budget; beyond it, decisions
use the deterministic policy and the report states exactly how many did. Every
metric is labelled with the provider that produced it, so a deterministic run
is never presented as a model run. This is how §17's numbers stay honest when a
run is bounded — CLAUDE.md forbids silently capping anything in the evaluation.

**The HTTP layer (added after the CLI).** `src/api/` serves the demo client. It
is a thin wrapper over `SparkSession`, which is a thin wrapper over the
supervisor graph: the consent gates reached over HTTP are the same
`interrupt()` calls in `src/graph/nodes.py`, resumed with the same
`Command(resume=...)`. There is no second implementation of the flow, which is
what lets a judge follow `POST /api/encounters/{id}/consent` down into
`src/safety/consent.py` and find the code `tests/test_consent.py` holds to
account. The checkpointer is SQLite, so an encounter halted at the reveal gate
survives the server restarting — the property that lets the gate be an interrupt
rather than a flag in a table.

Two details worth recording. The graph's thread id carries a per-run counter
(`{encounter_id}#{run_id}`): encounter ids are deterministic by design, so
without it a demo reset would find the *completed* checkpoint from the previous
take and replay its outcome — every retake showing the last take's result.
And `POST /api/demo/force-outcome` sets what the *simulated other party* does,
so each of the three endings can be filmed; it cannot reach what the viewer sees
for a given pair of answers, which is what invariant 3 protects.

**Graded numbers: Bedrock, decided but not yet run.** §16's routing table always
said the graded evaluation belongs on Bedrock so reported token costs are real.
That is now the decision. `uv sync --extra aws` is done and the routing is
configured — but there are no AWS credentials on the build machine, so **every
number currently in the report is Groq-derived or deterministic, and the report
labels it as such.** Until `SPARK_LLM_PROVIDER=bedrock uv run -m eval.run_arms`
has been run with credentials, "the graded numbers are on Bedrock" is a plan
rather than a fact. Setup: `docs/PILOT.md` §4.

**A finding on metric 1 (schema validation).** The Match, Continuity and
Communication agents originally asked the model for their full output model,
including `day`, `user_id` and `lockin_id` — facts the caller already holds. On
Groq's `openai/gpt-oss-20b` that produced a 37% first-attempt validation rate.
Narrowing the request to a *draft* containing only what the model should decide
(`MatchChoice`, `ContinuityDraft`, `ConversationDraft`) moved it to 97% on the
same model and the same prompts, with the single remaining miss being a provider
rate limit rather than a malformed output. The lesson generalises: a model asked
to reproduce bookkeeping it cannot know is given extra ways to fail, and the
metric then measures the prompt rather than the model.

**A finding on the model path's resilience.** Groq's free tier rate-limits on
tokens per minute. Left alone, every subsequent call in a run pays a timeout and
two backoff retries for nothing, and a six-week simulation stops finishing. Two
mechanisms handle it: a per-call fallback to the deterministic policy, and a
circuit breaker that stops calling a provider after five consecutive failures.
Both are counted and both are printed. The daily encounter is never blocked by a
model outage — a model failure degrades the *quality* of a selection, never the
availability of the product.

**A finding on open item 3 (the rematch cooldown).** `uv run -m eval.sweeps
--cooldown 0 7 14 30` measures what the guess costs. Because overlap is driven
by routine, a person's pool is largely the same faces each day, so a long
cooldown exhausts it: at 200 personas over six weeks, moving from no cooldown to
30 days cut encounters offered by roughly 60%. The default is left at 30 —
changing a product parameter because our own simulation preferred it would be
tuning the evaluation — but the number is now evidence rather than a feeling.

---

## 23. Open items

1. **Interviews — blocking.** Pressure-test Q3 fails until we have spoken to at least one person in our target. Everything else in this document rests on an unverified statement.
2. The fifth pressure-test question was not captured from the slide; recover it from the organisers.
3. Cooldown window before two users can be re-matched: currently a guess.
4. Lock-in ceiling of ten: the current product capacity; its attention trade-off is not yet measured.
5. Continuity note retention: 90 days by default. That number needs a real justification before any pilot.
6. Voice-channel safety screening is materially harder than text. Either specify the approach or scope screening to post-reveal chat and say so.
