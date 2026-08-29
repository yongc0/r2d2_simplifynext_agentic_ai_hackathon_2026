# Spark — code review status

**Updated:** 28 August 2026
**Repository:** `agentic_ai_hackathon_2026`

One current, internally consistent status report. Where something is only partly
done it says so in the same sentence.

---

## Verified today

```text
backend    242 passed, 1 skipped, no warnings   (uv run pytest)
frontend   175 passed,            no warnings   (npm test)
build      clean                                (npm run build)
whitespace clean                                (git diff --cached --check)
```

---

## Complete

**The experience, end to end.** onboarding → home → encounter → three-minute
call → consent → reveal → lock-in → continuity brief → date plan. Every route is
built; none renders a placeholder. Ten of ten client milestones.

**Both adapters.** `MockAdapter` is the default and needs no backend or key —
that is what the video is filmed against. `HttpAdapter` drives the real
supervisor graph, and the consent gates it reaches are the same LangGraph
`interrupt()` calls the CLI and the evaluation drive.

**All six product invariants and all seven UI invariants**, each with a test,
indexed in `invariants.test.tsx` so deleting one to make a feature pass fails
loudly.

**Eight agents**, four using a model and four deliberately deterministic —
consent, eligibility and identity-reveal are ordinary Python, per invariant 6.

### Defects found and fixed

| # | Defect | Held by |
| --- | --- | --- |
| 1 | **Consent-gate ordering.** A repeated `/respond` answered the reveal gate with two yes votes nobody cast; a later explicit `no` returned `mutual` plus a name. | `SparkSession._require_gate`; `test_api.py` |
| 2 | **A demo control could answer for the viewer.** "Both yes" plus a viewer pressing No still returned a person. | `mock.ts::submitConsent` returns before `forced` is read |
| 3 | **No route guards.** `/call/consent` typed into the address bar, plus one click, reached the reveal. | `routes/guard.ts`; direct-link tests |
| 4 | **A declined encounter stayed eligible for the call**, because both answers set `PENDING_ACCEPT`. | `Encounter.tsx`; verified to fail without the fix |
| 5 | **Restart recovery was not real.** `run_id` lived in memory, so a new process looked under the wrong thread. | Durable `spark_session_state`; genuinely new `SparkSession` objects in tests |
| 6 | **Consent timing leaked the outcome** — the delay started after the network call, and the mutual branch is slower. | `revealAt` quantises to whole windows from the click |
| 7 | **An invented Communication Agent prompt**, and a brief citing the wrong speaker. | Grounding derived from the transcript; ungroundable prompts cannot be constructed |
| 8 | **No way to leave a call early**, though three documents cited it as a safety mitigation. | `Call.tsx`; both exits share one function |
| 9 | **A lock-in appeared after mere acceptance**, carrying a name. | Gated on the reveal, client and server |
| 10 | **Guardian's check-in did nothing** — both answers called one handler, and nothing reached a server. | Distinct outcomes; `POST /guardian/check-in` → `IncidentLog` |
| 11 | **The Director trace chose its ending before it was known**, and could narrate a reveal beside a close-out. | Emitted by `submitConsent` from the actual result |
| 12 | **The Director feed opened with ~20 near-identical rows** and replayed the whole trace on every reconnect. | `mark_internal()`; 46 of 67 spans suppressed |
| 13 | **`/api/lockins` and `/api/briefs` were stubbed**, so the continuity half was filmable only on mocks. | Store on `SparkSession`; `advance-days` drives the real agent |
| 14 | **The encounter window never closed** — open from 9pm until the end of time. | `windowStatus()`, 21:00–22:00 |
| 15 | **Nothing was open at night**, including "late supper after everything else shuts". | Venue hours banded per venue |
| 16 | **The Date Agent tried only the first shared time**, discarding the pair's other free evenings. | Tries every shared bucket |
| 17 | **Guardian logged "NO ANSWER — escalate"** against someone who had just answered. | `answered` means *responded*; the concern is its own entry |
| 18 | **Frontend test warnings** (jsdom canvas, `act(…)`, Vite dynamic import). | All cleared |
| 19 | **Guardian closed the encounter only on the client.** The endpoint said "we have closed the encounter" while the server did nothing: `accept → concern → consent yes` returned `200 mutual` with the other person's name, opened a lock-in, and left date planning available. | Durable closure marker; `SparkSession.reveal_allowed` is the one boundary consent, lock-ins and dates all consult |
| 20 | **`mark_internal()` was a process-global.** While one request held it open for its starter search, another request's agent spans were tagged internal and silently vanished from that viewer's Director panel. | `ContextVar`, set/reset by token; a thread-isolation test that fails against the old global |

---

## Incomplete, and what that means

**No real-browser end-to-end tests.** The client is driven through the real
router and store in jsdom, which cannot perform an actual page load — so
deep-link and refresh behaviour is **verified at component level only**. The
guard logic is tested; the browser behaviour is not. Playwright would close it
and pulls several hundred megabytes of browser binaries, so it has not been
added unasked.

**Nothing durable survives a restart except the encounter.** The graph
checkpoint recovers across a genuinely new process, including after a demo
reset. The consent ledger, the lock-in store and the incident log are all
in-memory and rebuilt empty. Invariant 5 says consent events are append-only;
today that holds within a process and no further, and a test pins it so the code
and the documents agree.

**Nobody is watching the incident log.** Guardian's concern reaches a real
`IncidentLog` and now closes the encounter **on the server** — a durable marker
shuts the reveal path, survives a restart, and is consulted by consent, the
lock-in store and date planning alike. What is missing is a human: the log is in
memory and no operator sees it. The reply is worded to be true today, and a test
asserts it claims no review, no team and no follow-up.

**There is no auth.** One encounter per session, not per user. This alone rules
out a multi-person test.

**Bedrock has never been run.** No AWS credentials on this machine, so every
graded number is Groq-derived or deterministic, and the report says so.

---

## Only you can do these

- **One user interview.** Zero conducted; the pressure test fails until there is
  at least one.
- **Run the graded evaluation on Bedrock** — needs your AWS credentials, plus
  `SPARK_PRICE_*` or metric 4 reads "unpriced".
- **The deck (≤10 slides) and the recording (≤5 minutes).**
- **Commit, push, and any deploy.** Nothing has been committed.

---

## Recommendation

**Ready to commit.** Both suites and the build are clean; no credentials or
artefacts are staged.

**Ready for a Netlify draft deployment.** No route renders a placeholder, the
mock path runs end to end, and the public build cannot reach a backend. Promote
to `--prod` only after the deep-link routes are smoke-tested in a real browser —
the gap the missing Playwright suite leaves.

**Do not deploy the FastAPI backend.** No auth, one shared in-memory session.

**In the video and deck:** the public site runs MockAdapter, so the Director
panel there is a scripted trace, not live OTEL spans. That claim is only true
running locally against the API. And the pre-registered result is negative —
Spark 12.6% vs random 12.6%, p = 0.97 — and should be shown as it stands.
