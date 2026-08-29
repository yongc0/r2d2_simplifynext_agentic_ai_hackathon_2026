# PILOT.md — running Spark on real devices

How to stand the system up for a live test, and — just as important — an honest
list of what is still stubbed.

Read alongside `CLAUDE.md` (invariants), `docs/ARCHITECTURE.md` (design) and
`docs/FRONTEND.md` (the client).

---

## 1. What works today

| Piece | State |
|---|---|
| Supervisor graph, agents, evaluation | ✅ Complete, 242 tests |
| FastAPI backend over the real graph | ✅ Built — see §3 |
| Demo client, all screens | ✅ Complete — 10 of 10 milestones, 164 tests, guarded routes, no stubs |
| **Director panel** | ✅ Built — toggle with `D`, live token + elapsed counters |
| **`HttpAdapter`** | ✅ Built — `VITE_API=http`, verified end to end through the Vite proxy |
| Demo controls (client UI) | ✅ Built — behind `?demo=1`, every action awaited |
| Guardian | ✅ Built — in-app reminder, then a private check-in |
| **Real voice (LiveKit)** | ❌ Not started |
| **HTTPS tunnel** | ❌ Not started |
| **Telegram notifications** | ❌ Not started |

**A live 3-person voice test is not reachable yet.** The bottom three rows are
the whole of it, and none has been started. §7 lists what each needs.

---

## 2. Start everything

Two processes, two terminals. Nothing here needs a key.

```bash
# terminal 1 — the API, on :8000
cd spark
uv sync --extra dev
uv run -m src.api

# terminal 2 — the client, on :5173
cd web
npm install
npm run dev
```

Open http://localhost:5173. Check the backend with:

```bash
curl -s http://127.0.0.1:8000/api/health
```

```json
{"ok":true,"provider":"groq","modelReasoning":"openai/gpt-oss-20b",
 "modelFast":"openai/gpt-oss-20b","callSeconds":180,"worldUsers":60}
```

`provider` is reported on purpose: a deterministic-policy run must never be
mistaken for a model run.

### Which adapter is in use

```bash
npm run dev                 # MockAdapter — no backend needed. THE DEFAULT.
VITE_API=http npm run dev   # HttpAdapter — talks to the FastAPI process
```

`MockAdapter` stays the default on purpose: FRONTEND.md §4 requires the demo to
exist without a backend, and it is what the submission video is filmed against.
`VITE_API=http` is verified working end to end — open → respond → call-script →
consent (mutual, with an identity) — through the Vite `/api` proxy, plus the SSE
agent feed.

### The Director panel

Press **`D`**. Hidden by default so the phone can be filmed clean and then the
panel revealed. Docks to the right of the device frame on desktop only; the
space is reserved from first paint, so switching it on does not move the phone
mid-take.

Rows are colour-coded per agent, monospace, click to expand the rationale the
agent returned. Two of the six graded metrics run live in the header: **token
count** and **elapsed wall time**. On a deterministic run it says "no model
calls" rather than "$0.00" — a run with no model spend is not a free run.

On `VITE_API=http` the rows are **real OTEL spans** streamed from the backend
over SSE, not a scripted animation.

---

## 3. The API

Every route drives the **same supervisor graph** the CLI and the evaluation
drive. The consent gates reached over HTTP are the same LangGraph `interrupt()`
calls in `src/graph/nodes.py`, resumed with the same `Command(resume=...)`.
There is no second implementation of the flow.

| Route | Purpose |
|---|---|
| `GET /api/health` | Provider, model ids, call length, world size |
| `POST /api/encounters` | Today's encounter. Runs to the accept gate and halts. `409` = a quiet day. Idempotent: a repeat returns the same encounter |
| `GET /api/encounters/{id}` | The card again |
| `POST /api/encounters/{id}/respond` | Answer the notification — resumes gate 1. `409` unless the accept gate is the pending one |
| `GET /api/encounters/{id}/call-script` | Amplitude track for the waveform (**stubbed**, see §6) |
| `POST /api/encounters/{id}/consent` | Answer the reveal gate — resumes gate 2. `409` unless the reveal gate is the pending one |
| `POST /api/onboarding/extract` | One turn of intake, run by the real Onboarding Agent |
| `GET /api/encounters/{id}/dates` | Three date paths from the Date Agent. `409` before a mutual yes |
| `GET /api/lockins`, `GET /api/briefs` | The connections open in this run, and what Continuity would surface |
| `POST /api/demo/advance-days` | Move the simulated clock — week 1 to week 5 inside a five-minute take |
| `POST /api/encounters/{id}/guardian/check-in` | Record the private check-in answer |
| `GET /api/events` | Director panel feed, Server-Sent Events from real OTEL spans |
| `POST /api/demo/reset` | Deterministic reset (§8 of FRONTEND.md) |
| `POST /api/demo/force-outcome` | Force the other party's answer, to film each branch |

### A full encounter, by hand

```bash
EID=$(curl -s -X POST localhost:8000/api/encounters | jq -r .encounterId)
curl -s -X POST localhost:8000/api/encounters/$EID/respond \
     -H 'Content-Type: application/json' -d '{"accept":true}'
curl -s -X POST localhost:8000/api/encounters/$EID/consent \
     -H 'Content-Type: application/json' -d '{"yes":true}'
```

### Filming all three outcomes

```bash
for o in mutual no_response declined; do
  curl -s -X POST localhost:8000/api/demo/reset > /dev/null
  curl -s -X POST localhost:8000/api/demo/force-outcome \
       -H 'Content-Type: application/json' -d "{\"outcome\":\"$o\"}"
  # ...then open, respond, consent as above
done
```

`no_response` and `declined` return `{"outcome":..., "person":null}` — identical
but for a label the client cannot act on, because `CloseOut` takes no props.
That is invariant 3 at the API boundary.

---

## 4. Environment variables

All optional. Everything runs with none of them set.

| Variable | Default | Purpose |
|---|---|---|
| `SPARK_LLM_PROVIDER` | auto | `deterministic` \| `groq` \| `bedrock` |
| `GROQ_API_KEY` | — | Free tier, local development |
| `AWS_DEFAULT_REGION` | `ap-southeast-1` | Bedrock region |
| `SPARK_BEDROCK_REASONING_MODEL` | Sonnet 4.5 | Judgement calls |
| `SPARK_BEDROCK_FAST_MODEL` | Haiku 4.5 | Extraction, briefs |
| `SPARK_PRICE_*_IN` / `_OUT` | unset | USD per Mtok; unset ⇒ report says "unpriced" |
| `SPARK_LLM_CALL_BUDGET` | 200 | Model calls per run; the rest use the deterministic policy, and the report says how many |
| `SPARK_SIM_SEED` | 42 | Deterministic takes |

Secrets go in `spark/.env`, which is gitignored. Never commit one, never log
one, never put one in an OTEL span attribute — `src/telemetry/trace.py` scrubs
any attribute whose name looks like a credential.

### Bedrock, for the graded numbers

Decided: **the graded evaluation runs on Bedrock**, so reported token costs are
real (CLAUDE.md's model-routing table).

```bash
cd spark
uv sync --extra aws          # done — langchain-aws 1.7.3, boto3 1.43.78
echo 'SPARK_LLM_PROVIDER=bedrock' >> .env
echo 'AWS_DEFAULT_REGION=ap-southeast-1' >> .env
# plus credentials: aws sso login --profile <p>, or AWS_ACCESS_KEY_ID/SECRET
uv run -m eval.run_arms && uv run -m eval.report
```

> ⚠️ **This has not been run.** There are no AWS credentials on this machine —
> no `~/.aws`, no `AWS_*` environment variables. The dependency is installed and
> the routing is configured, but **every number currently in the report is
> Groq-derived or deterministic**, and the report labels it as such. Until
> someone runs the command above with credentials, "the graded numbers are on
> Bedrock" is a plan, not a fact.

Also set `SPARK_PRICE_REASONING_IN`/`_OUT` from Bedrock's current published
rates, or metric 4 will read `"N calls, unpriced"` and cost-per-connection will
be `n/a`. We deliberately do not hardcode a price that goes stale.

---

## 5. Recording

- Record the browser at 1080p. At ≥768px the app renders in a 390×844 device
  frame on a neutral backdrop; below that it is full-bleed mobile.
- No FOUC: the background is painted in `index.html` before React mounts.
- No network fonts: Inter is bundled as local `.woff2`.
- No scrollbars in frame: the screen area clips and scrolls without chrome.
- `POST /api/demo/reset` before each take — same seed, same take.

---

## 6. What is stubbed, and why

Stated here rather than discovered by a judge.

- **The voice bridge is a mock.** `spark-voice` returns a scripted call; there
  is no audio. `GET /call-script` serves an amplitude track so the waveform has
  something to draw. **The 180-second stop does not depend on it** — that is
  enforced in `connect_call`, where duration is not a parameter.
- **The lock-in store is now on the session, not only in the simulation.**
  `/api/lockins` and `/api/briefs` are real, opened by the same mutual reveal
  the graph performs, and `POST /api/demo/advance-days` drives the actual
  Continuity Agent forward. It is still per-process and in memory: a restart
  loses the lock-ins, though the encounter checkpoints survive.
- **Overlap detection is simulated.** Nobody's real location is used anywhere.
  Overlaps come from synthetic routines in `src/sim/world.py` — a coarse cell
  and a time bucket, historical only. There is no live-proximity code path and
  there will not be one (ARCHITECTURE §13.3).
- **There is no real Singpass integration or identity verification.** The
  onboarding UI contains an explicitly labelled interactive concept that
  accepts no credentials, identity numbers or personal data and makes no
  external request. `verification_tier` remains a synthetic field on a
  synthetic persona.
- **There is no auth.** The server cannot tell two browsers apart, so "one
  encounter per person per day" is held in the session rather than per user.
  Fine for a demo, and the single reason a three-person test is not reachable.
- **Trust & Safety screens text, not audio.** Onboarding intake and post-reveal
  messages are screened; the call itself is not. Voice-channel screening is
  materially harder, and the call's mitigations are structural instead: three
  minutes, anonymous both sides, no identity without a mutual yes, either party
  can end it.
- **Continuity note retention is 90 days** and that number is still unjustified.

---

## 7. What a live 3-person test still needs

None of this is built. Listed with the decisions each one needs.

### 7.1 Real voice (LiveKit)

- `POST /api/encounters/{id}/token` issuing a JWT signed with
  `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`, room = encounter id, identity = an
  opaque per-encounter participant id.
- **Participant identity must be opaque in three places, not one.** LiveKit
  exposes `identity`, `name` and `metadata` on every participant to the other
  side. All three must be non-derivable — `HMAC(encounter_id + user_id, secret)`
  truncated, not the user id and not the handle.
- Audio only. No video track, no camera permission, ever.
- **The 180-second stop must be server-enforced.** I checked
  `CreateRoomRequest`: LiveKit exposes `empty_timeout`, `departure_timeout` and
  `max_participants` — **there is no native max-duration field**. So it needs
  scheduled room deletion at 180s **plus a ~185s JWT `exp` as the backstop**: a
  scheduled task dies with the process, but an expired token cannot be used to
  rejoin.
- **Do not enable recording.** A recorded anonymous call is a stored voiceprint
  of two people who have not agreed to identify themselves to each other.
- **Open question:** does the 180s start when the first party joins, or when
  both are connected? If the first, a late joiner loses their time; if the
  second, a no-show holds the room open. Not specified — needs a decision.
- **Open question:** if a user denies microphone permission, the encounter
  cannot become a call. It should end ABANDONED — and critically, the *other*
  party must not be able to tell that apart from a no-show (invariant 2).
- It should be implemented **behind the existing `spark-voice` MCP tool**, not
  beside it, or the "every external capability is an MCP server" claim (§11.3)
  weakens and the simulation and the pilot stop running the same graph.

### 7.2 HTTPS tunnel

- Vite already reserves `/api`; the proxy stanza is in `web/vite.config.ts`,
  commented out pending `HttpAdapter`.
- `npm run tunnel` → cloudflared quick tunnel at the Vite port, so **one** tunnel
  exposes both halves.
- Quick tunnels get a new URL per restart, so `PUBLIC_URL` must be read at
  startup and the Telegram webhook re-registered each time.

### 7.3 Telegram

- `python-telegram-bot`, token in `TELEGRAM_BOT_TOKEN`.
- `/start` captures `chat_id`, linked to a Spark user by a one-time code.
- The notification carries **no** identifying information — same invariants as
  the in-app screen.
- Accept and decline happen **in the app**, never via inline buttons: the
  consent gate lives in one place, and a Telegram button would leak response
  timing outside it.

---

## 8. Known issues, queued

A code-review audit on 27 August found one serious defect and several smaller
ones. What it found, and where each stands, is below. The audit's own notes are
in `CODE_REVIEW_HANDOFF.md`.

### Fixed

1. **A consent-gate ordering vulnerability.** `Command(resume=...)` is delivered
   to whichever LangGraph interrupt is pending, and neither `accept()` nor
   `consent()` checked which one that was. A repeated `POST /respond` therefore
   answered the REVEAL gate with two yes votes nobody had cast, and the user's
   later explicit `no` came back `mutual`, with the other person's name.
   Reproduced through the real app; closed by `SparkSession._require_gate`,
   which reads the pending interrupt from the checkpoint and refuses anything
   else with a 409. `tests/test_api.py` now holds the line, including a
   parameterised assertion that an explicit no never reveals after ANY malformed
   sequence.

2. **Consent timing leaked the outcome.** The close-out delay started after the
   network call instead of before it, and the mutual branch does strictly more
   work — so the wait was longer when the answer was yes, which a stopwatch could
   read before the screen said anything. The wait is now measured from the click
   and quantised to whole windows.

3. **An invented Communication Agent prompt.** "You both mentioned early
   mornings" was evidenced by a certification exam and some birdwatching. The
   evidence is now looked up from the transcript by topic id, so a prompt
   claiming a commonality only one speaker raised cannot be built. The continuity
   brief was also attributing the user's own words to the other person.

4. **The call could not be left early**, though three documents cited "either
   party can end it" as a safety mitigation. Built, and it shares one exit with
   the timer so nothing downstream can tell the two apart.

5. **A lock-in appeared after mere acceptance.** `MockAdapter.getLockIns()` keyed
   off the notification being accepted, handing back a name and an avatar seed
   before any reveal.

6. **`POST /api/encounters` was not idempotent**, and a second call opened a
   second encounter belonging to a different person.

7. **Frontend test warnings** — jsdom canvas, React `act(...)`, and a Vite
   dynamic-import warning — are all cleared, so a clean run looks clean.

8. **`web/src/api/wire.ts` cited a test that did not exist.**
   `spark/tests/test_wire_contract.py` now exists and checks the intent values,
   the encounter states, the onboarding keyword lists and the call transcript.

### Still open

1. **No real-browser end-to-end tests.** The client is tested through the real
   router and store in jsdom, which cannot perform an actual page load, so
   deep-link and refresh behaviour is **verified at component level only**. A
   Playwright suite would close it and pulls several hundred megabytes of
   browser binaries; it has not been added unasked.

2. **The consent ledger does not survive a restart.** The encounter does — that
   is tested against genuinely new sessions. The history does not:
   `ConsentLedger` is an in-memory list rebuilt empty at startup. The reveal
   still behaves correctly, because it needs `call_ended` (checkpointed) and
   reveal-stage records (written again on resume). Invariant 5 says consent
   events are append-only; today that holds within a process and no further,
   and `test_the_consent_history_does_not_survive_a_restart` says so out loud.
   The lock-in store has the same limit.

3. **Nobody is watching the incident log.** Guardian's check-in reaches a real
   `IncidentLog` through `POST /guardian/check-in`, and a concern now closes the
   encounter **on the server**: a durable marker shuts the reveal path, so a
   later `consent yes` returns no identity, opens no lock-in and refuses date
   planning, and the closure survives a restart. What is still missing is a
   human: the log is in memory and no operator sees it. The reply is worded to
   be true today — a test asserts it claims no review, no team and no follow-up
   — and what an organisation should do with an entry remains a policy question
   this MVP does not answer.

4. **There is no auth.** One encounter per SESSION, not per user. Two phones
   would share one encounter and one side of the consent gate. This alone rules
   out the three-person test.

5. **`pkill` does not kill the Windows Python process.** Restarting the API
   needs PowerShell `Stop-Process`, or the old code keeps serving.

6. **Bedrock has never been run** — see §4. The graded numbers are still
   Groq/deterministic.

### Closed since the last review

- **`/api/lockins` and `/api/briefs` were stubbed.** The store moved onto
  `SparkSession`, opened by the same `reveal_permitted` check that guards the
  identity. `advanceDays` works over HTTP and drives the real Continuity Agent.
- **The Director feed opened with a wall of near-identical rows.** The starter
  search is machinery, not agent work; it runs inside `mark_internal()` and the
  feed drops it. 46 of 67 spans in a full encounter are now suppressed, and the
  panel opens on the match. The spans stay in the trace file for debugging.
- **The feed replayed the whole trace to every new connection**, so a reset
  stacked the previous take on top of the new one. It now starts from the
  present.

## 9. Still-open decisions

Carried from the build, unchanged:

1. **Interviews — blocking.** Zero conducted. ARCHITECTURE §23.1 and
   pressure-test Q3 both fail until at least one person in the target group has
   been spoken to.
2. **Rematch cooldown.** Measured but not decided: 0d → 980 encounters,
   **7d → 656 encounters and the most connections**, 30d → 235. Default left at
   30 as specified. `uv run -m eval.sweeps --cooldown 0 7 14 30`.
3. **How the deck frames the negative pre-registered result.** Spark 12.6% vs
   random 12.6%, p=0.97. Reported as it stands; the framing is a presentation
   decision.
4. **Whether real people's data may enter the system for the pilot.** CLAUDE.md
   says "do not use real personal data anywhere". A live test with real voices,
   real names at reveal, and real Telegram chat ids is a genuine change in risk
   profile, even with three consenting participants who know it is a test.
