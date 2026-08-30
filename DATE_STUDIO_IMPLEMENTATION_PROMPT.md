# Spark Date Studio — product plan and Claude Code implementation brief

> Give this entire file to Claude Code. It is both the product decision record
> and the execution prompt for the first implementation slice.

## Objective

Extend Spark's existing post-reveal Date Agent into a **Date Studio** that gives
people a useful reason to return after matching.

The retention loop is not "browse more people". It is:

```text
Mutual reveal
    → choose a lock-in
    → set today's constraints
    → receive three grounded date plans
    → save, reject or refine
    → tell Spark what worked
    → inspect or correct what Spark learned
    → receive better plans next time
```

The implementation must demonstrate that Spark **plans, remembers and adapts**.
It must not claim to train a model continuously. Improvement comes from durable,
auditable preference memory and deterministic re-ranking.

## What already exists — extend it, do not rebuild it

Read these files before changing anything:

- `ARCHITECTURE.md`, especially §§13.4, 13.6, 13.7 and 15
- `spark/src/agents/date.py`
- `spark/src/agents/continuity.py`
- `spark/src/api/app.py`
- `spark/src/api/session.py`
- `spark/src/api/schemas.py`
- `spark/src/schemas/agents.py`
- `spark/src/schemas/core.py`
- `spark/src/mcp/services.py`
- `spark/src/mcp/registry.py`
- `spark/tests/test_date.py`
- `spark/tests/test_api.py`
- `web/src/screens/Dates.tsx`
- `web/src/screens/LockIns.tsx`
- `web/src/api/adapter.ts`
- `web/src/api/http.ts`
- `web/src/api/mock.ts`
- `web/src/api/types.ts`
- `web/src/store/useSpark.ts`
- the existing frontend test files

The repository already has:

- A deterministic Date Agent producing up to three different date paths.
- A reveal-gated date endpoint.
- Lock-ins created only after mutual post-call consent.
- Shared interests and coarse shared availability.
- Continuity notes scoped per owner.
- Commercial-partner labels that cannot be omitted.
- A `/dates` screen and matching mock/HTTP adapter contracts.
- Guardian safety closure consulted by identity-bearing paths.

Preserve those guarantees. Refactor only where necessary to create one coherent
Date Studio rather than adding a second unrelated recommendation system.

---

## Product decisions

### 1. Where Date Studio lives

Add a first-class `/plans` section.

- `/plans` — lists revealed, active lock-ins and lets the viewer choose a person.
- `/plans/:lockInId` — preference boxes, recommendations and feedback for that
  connection.
- A "What Spark remembers" panel is accessible from `/plans` and the planner.
- Existing links from `/lockins` should lead into the appropriate plan route.
- Preserve `/dates` temporarily as a compatibility redirect or wrapper. Do not
  leave two implementations that can drift.

Do not introduce a global bottom navigation across calls, consent or Guardian
screens in this slice. Add clear entry points from Home and Lock-ins instead.

### 2. Date planning is post-reveal only

A date plan can name activities and therefore remains behind the same boundary
as identity:

- The lock-in must exist.
- It must belong to the current demo viewer.
- It must not be released.
- Its encounter must have a mutual reveal.
- It must not have a Guardian safety closure.
- Both users must allow date suggestions.

The server is authoritative. A React redirect is helpful UX, never the safety
boundary.

### 3. Use fixed controls, not an open chat box

The planning form uses selectable boxes/chips. Initial dimensions:

| Dimension | Values |
| --- | --- |
| Mood | `easy`, `playful`, `adventurous`, `meaningful` |
| Budget | `free`, `under_20`, `under_50`, `flexible` |
| Duration | `one_hour`, `two_hours`, `whole_evening` |
| Energy | `low`, `medium`, `high` |
| Format | `food`, `activity`, `outdoors`, `learning`, `event` |
| Time | One of the pair's genuinely shared coarse availability buckets |

The UI may preselect remembered values but must show that it did so and let the
user change them before generating a plan.

Accessibility and dietary constraints are important, but do not pretend the
current venue catalogue supports them. Add them only if the same change adds
structured venue attributes and hard-filter tests. Never display an unverified
accessibility or dietary claim.

Do not add an exact address, live position, distance, map or inferred meeting
area. A mutually selected broad area can be a later feature once authentication
and real venue data exist. Historical overlap data must never influence a plan.

### 4. Return three meaningfully different plans

When enough compatible options exist, label the three shapes for the user:

1. **Easy** — low commitment and simple.
2. **Something new** — a more novel shared-interest option.
3. **Keep it light** — lower cost, time or energy.

These labels are presentation categories, not invented claims about the users.
The underlying paths must still differ in lead activity.

Each plan card shows:

- A concise itinerary.
- Time bucket, duration and budget band.
- Why it fits these two people.
- The explicit preferences or shared interests supporting it.
- A commercial-partner label beside every partner stop.
- Actions: `Save`, `Not for us`, and `Refine`.

If fewer than three honest plans exist, return fewer and explain why. Never pad
the list with a weak or ungrounded option.

### 5. Memory is visible, scoped and correctable

Use two scopes:

#### User preference memory

Facts that can help this user across connections, for example:

- Prefers quieter or lower-energy plans.
- Usually chooses plans below $20.
- Often wants one-hour activities.
- Explicitly likes learning activities.

#### Connection memory

Facts that apply only to one lock-in, for example:

- This pair saved a coffee-and-walk style plan.
- This pair rejected crowded evening events.
- They have already been shown a particular activity.

Connection memory must never affect a different lock-in. One person's private
feedback must never be returned to the other person as a quote or rejection.

Every memory item must carry:

- Stable ID.
- Owner ID, derived by the server rather than accepted from the client.
- Scope: `user` or `lockin`.
- Optional lock-in ID, required for lock-in scope.
- Dimension and value.
- Source: `explicit` or `feedback`.
- Confidence in the range 0–1.
- Created and updated timestamps.
- Active/deleted state or a recoverable deletion strategy.

The interface must let the user:

- See what Spark remembers.
- See whether each item was explicitly selected or learned from feedback.
- Correct a value.
- Delete a memory item.
- Choose whether a one-off planning constraint should be remembered.

Temporary context such as "I am tired tonight" must not become durable memory
unless the user selects **Remember this preference**.

### 6. Learning means deterministic adaptation

Use a transparent scoring pipeline:

1. Hard-filter on consent, lock-in eligibility and shared availability.
2. Require at least one genuinely shared interest for every path.
3. Score current request constraints.
4. Add preference-memory fit.
5. Add a small reward for previously saved styles.
6. Add a penalty for dimensions explicitly rejected for this lock-in.
7. Add a repetition penalty so the same lead activity does not dominate.
8. Rank on fit. Only after ranking may commercial-partner metadata be attached.

Explicit preferences have confidence `1.0` and always outweigh inferred
feedback. Feedback-derived confidence must be capped below explicit confidence
and move gradually. Do not treat a single rejection as a permanent dislike.

The rationale must cite real evidence available to the scorer. Never write a
personalised explanation first and attempt to justify it afterward.

### 7. Feedback is structured

Actions:

- `saved`
- `rejected`
- `completed`

Rejection reason chips:

- `too_expensive`
- `too_long`
- `too_active`
- `too_quiet`
- `too_crowded`
- `wrong_time`
- `already_done`
- `not_our_style`

Ask about recommendation quality, not whether the relationship or date was
successful. Avoid questions such as "Did they like you?".

Feedback must be idempotent. Repeating the same request must not double-learn.
The user can change their feedback, with the latest active feedback determining
the score while the audit record remains understandable.

### 8. Ethical retention

This slice should make returning useful without introducing manipulation.

Build:

- Saved plans.
- Better next recommendations.
- A clear memory-control surface.
- A gentle entry point from an active lock-in.

Do not build:

- Streaks.
- Swipe feeds.
- Manufactured urgency.
- "They are waiting for you" messages.
- Notifications exposing rejection or private feedback.
- Compatibility percentages.
- Infinite recommendations.

The intended product metric is **weekly meaningful planning actions per active
lock-in**, not session length.

---

## Phase 1 implementation — execute this phase now

Implement one complete vertical slice across the deterministic provider,
backend API, MockAdapter, HttpAdapter and React UI.

### A. Domain schemas

Add strict Pydantic models and matching TypeScript interfaces for:

- `DatePlanningPreferences`
- `DatePlanRequest`
- `DateMemoryItem`
- `DatePlanRecord`
- `DatePlanFeedback`

Prefer enums/literals to free text. Use `extra="forbid"` in Python. Bound list
sizes and strings. Ensure wire aliases follow the repository's current camelCase
convention.

Extend `DatePath` and its API output only with fields the UI truly renders:

- `shape`: `easy | new | light`
- `budget_band`
- `duration_band`

Do not add identity, address, coordinates, cell, distance or partner-ranking
fields.

### B. Durable local memory

The claim that the agent improves over time must survive a process restart.
Implement a small repository abstraction with a local SQLite implementation.
Use the existing checkpoint database or a clearly documented adjacent database;
do not store this only on `SparkSession` or in `WORLD`.

Required stored records:

- Date preference memory.
- Generated plan snapshots sufficient to validate later feedback.
- Date-plan feedback.

Create tables with `CREATE TABLE IF NOT EXISTS`; no destructive migration.
All queries must be parameterised.

Provide an interface narrow enough that an AgentCore Memory-backed adapter can
replace SQLite later. Do not claim AgentCore persistence is currently live.

The ordinary demo reset should clear Date Studio memory and plans so recorded
takes remain deterministic. A normal process restart must preserve them.

### C. Date Agent ranking

Refactor the existing Date Agent rather than creating another agent.

- Accept a validated planning request and applicable memory items.
- Keep the existing venue lookup and commercial-ranking rule.
- Produce deterministic, reproducible scores.
- Return no plan when consent, shared interests, availability or honest venue
  options are missing.
- Include trace attributes for number of candidates, applied preference count,
  feedback count and final path count. Do not put private memory text into spans.

Add a small scorer or explanation helper if that makes evidence grounding easy
to test independently.

### D. Backend API

Use lock-in-based routes for the new planner:

```text
GET    /api/plans
GET    /api/lockins/{lockin_id}/date-preferences
PUT    /api/lockins/{lockin_id}/date-preferences
POST   /api/lockins/{lockin_id}/date-plans
POST   /api/date-plans/{plan_id}/feedback
GET    /api/date-memory
PATCH  /api/date-memory/{memory_id}
DELETE /api/date-memory/{memory_id}
```

Exact response envelopes may follow existing conventions, but keep the adapter
contract consistent.

For every route:

- Derive the viewer from the server-side lock-in/session context.
- Never accept `owner_id` from the client.
- Return `404` for an unknown lock-in or memory item.
- Return `409` when the lock-in exists but planning is not currently permitted.
- Validate feedback against a stored plan belonging to the same viewer and
  lock-in.
- Make mutation routes idempotent where practical.

Preserve the old encounter-based date endpoint as a thin compatibility wrapper
or deprecate it internally without breaking existing tests and adapters.

### E. Frontend experience

Create or refactor into:

- `PlanHub` — active lock-in selector, saved-plan summary and memory entry point.
- `DateStudio` — fixed preference boxes and Generate action.
- `DatePlanCard` — the three shapes, evidence, labels and feedback actions.
- `DateMemoryPanel` — view, correct and delete remembered preferences.

UX requirements:

- Empty `/plans` state explains that planning opens after a mutual reveal.
- A direct link cannot render a name or plan without an eligible lock-in.
- Selection works with keyboard and screen readers.
- Loading, empty and failure states are explicit.
- The form works without typing.
- Generating twice with unchanged inputs does not silently accumulate duplicate
  memory or feedback.
- `prefers-reduced-motion` remains respected.
- No plan or memory item appears in the Director panel as if it were user text.

Update both adapters. Mock behaviour must exercise the same state transitions
and learning rules closely enough for the public Netlify demo, while the UI must
not claim its mock trace is live OTEL.

### F. Tests

Add regression tests before considering the phase complete.

#### Backend/domain

- Planning is refused before mutual reveal.
- Planning is refused after Guardian closure.
- Planning is refused for a released or foreign lock-in.
- Owner identity is derived server-side.
- User memory never appears in another user's read.
- Lock-in memory never affects another lock-in.
- Explicit preference outranks inferred feedback.
- One rejection changes ranking gradually, not absolutely.
- Temporary constraints are not stored unless explicitly remembered.
- Feedback is idempotent.
- A changed feedback record does not double-count the old value.
- Date memory, plan and feedback survive a genuinely new process.
- Demo reset clears the Date Studio state.
- Partner status never influences ranking and is always labelled when returned.
- No output schema contains address, coordinate, cell, distance or identity.
- Every rationale is grounded in an explicit/shared preference used by scoring.

#### Frontend

- `/plans` shows only eligible lock-ins.
- Empty state appears without an eligible lock-in.
- Every fixed option is selectable without typing.
- Remembering a preference is visibly opt-in.
- Three distinct shapes render when available.
- Short or empty results explain why.
- Saved/rejected feedback reaches the adapter once.
- A rejected reason changes the next mock ranking.
- Memory can be viewed, corrected and deleted.
- Direct-link and safety guards expose no plan or identity.
- Commercial partners are labelled beside the affected stop.
- Existing encounter, consent, Guardian and onboarding tests remain green.

### G. Documentation

Update:

- `ARCHITECTURE.md`
- `docs/FRONTEND.md`
- `docs/PILOT.md`
- `README.md`
- `CODE_REVIEW_HANDOFF.md`

State precisely:

- Local SQLite preference memory is live.
- AgentCore Memory is the target adapter, not a completed production integration.
- The recommender improves by re-ranking from auditable memory; it does not
  retrain a foundation model.
- Pair collaboration, booking and notifications remain incomplete.
- The Netlify public build uses MockAdapter.

---

## Phase 2 — plan next, do not implement silently

After Phase 1 is reviewed, add collaborative proposals:

```text
DRAFT → SHARED → WAITING_FOR_PRIVATE_RESPONSES → CONFIRMED | EXPIRED
```

- Each user privately saves, rejects or requests refinement.
- Neither user sees which option the other rejected.
- The shared result says only which plan was mutually confirmed.
- One user's private memory and feedback remain private.
- This phase requires a real notion of two authenticated viewers; do not simulate
  it while claiming multi-user collaboration is complete.

## Phase 3 — explicitly out of scope for this implementation

- Real venue names, maps or routing.
- Booking, payment or external calendar writes.
- Push notifications.
- Real-time partner chat.
- Production AgentCore Memory credentials or deployment.
- Model fine-tuning or online training.
- Relationship-success scoring.

---

## Verification commands

Run the repository's existing commands and report exact results:

```text
cd spark
uv run pytest

cd ../web
npm test
npm run build

cd ..
git diff --check
git status --short
```

Also perform staged/working-tree hygiene checks for real `.env` files,
credentials, `node_modules`, `dist`, SQLite files, `tsbuildinfo` and backups.
Do not delete or overwrite unrelated user work.

## Definition of done for Phase 1

Phase 1 is complete only when a reviewer can demonstrate this sequence using
both adapters:

```text
mutual reveal
→ open Plans
→ select a lock-in
→ choose fixed constraints
→ generate grounded options
→ reject one with a reason
→ generate again and observe a justified ranking change
→ save one
→ inspect exactly what Spark learned
→ correct or delete that memory
→ restart the backend and see permitted memory persist
```

No identity or date plan may appear before mutual reveal or after a Guardian
closure. That safety condition takes precedence over every retention feature.

## Claude Code execution instructions

Implement **Phase 1 only** now.

1. Inspect the current implementation and reconcile this document with actual
   types and conventions before editing.
2. If an existing abstraction already covers a requirement, extend it instead
   of duplicating it.
3. Keep the Date Agent deterministic and evidence-grounded.
4. Preserve all existing safety and consent invariants.
5. Add tests alongside each backend and frontend behaviour.
6. Run the complete verification suite, not only new tests.
7. Update the documentation with implemented facts and clearly labelled gaps.
8. Stop and report if implementing a requirement would require auth, real AWS
   credentials, real user data, deployment or a destructive migration.

At the end, report:

- Files changed and the purpose of each group.
- The implemented user journey.
- The persistence and scoring design.
- New tests and exact final counts.
- Any remaining gaps or claims that must not be made.
- Whether the change is ready to commit.

Do not commit, push, deploy, install Playwright, add real credentials, or add
real personal/venue data unless separately authorised.
