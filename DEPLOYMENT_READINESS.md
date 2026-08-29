# Spark deployment-readiness checklist

**Reviewed:** 28 August 2026

**Current decision:** **do not deploy to real users yet.** Spark is a strong
simulated hackathon demo, but it is not a production or real-user pilot
service. Tick an item only when its acceptance evidence is linked in the pull
request or release record.

## Verified baseline

- [x] Backend regression suite passes: `198 passed, 1 skipped`.
- [x] Frontend regression suite passes: `169 passed`, with **no warnings**.
- [x] Frontend production build succeeds: `npm run build`.
- [x] API health endpoint responds on the local server.
- [x] Core simulation guards have tests: dual consent, silent close-out, no
  location/identity before reveal, and the 180-second call limit.
- [x] The default demo is deterministic and uses synthetic data.

The passing suites establish **demo correctness**, not production readiness.

The frontend warnings are cleared: the jsdom canvas stack, the React
`act(...)` warnings and the Vite dynamic-import warning are all gone, so a
clean run now looks clean and the next real warning will be visible.

### Fixed since the last review

- [x] **A consent-gate ordering vulnerability, found and closed.** The API
  resumed the LangGraph interrupt without checking WHICH gate was pending,
  so a repeated `POST /respond` answered the reveal gate with two yes votes
  nobody had cast, and a later explicit `no` returned `mutual` with the other
  person's name. Reproduced through the real app, fixed in
  `SparkSession._require_gate`, and regression-tested in `tests/test_api.py`,
  which asserts an explicit no never reveals after any malformed sequence.
- [x] **Consent timing no longer leaks the outcome.** The close-out delay
  started after the network call rather than before it, so the slower mutual
  branch was measurable on a stopwatch. The wait is now quantised to whole
  windows from the moment the person answers.
- [x] **The Communication Agent's scripted prompt is grounded.** Its evidence
  is now looked up from the transcript by topic id rather than written beside
  it; a prompt claiming a commonality only one speaker raised cannot be
  constructed. The continuity brief also cites the right speaker.
- [x] **Either party can now end the call**, which the safety argument had
  claimed for three milestones without it being built.
- [x] **A lock-in requires a mutual reveal.** `MockAdapter.getLockIns()` keyed
  off notification acceptance, returning a name to anyone who agreed to take
  the call.
- [x] **The demo control could answer for the viewer.** `MockAdapter` combined
  the forced peer outcome with the local answer, so "both yes" plus a viewer
  pressing No still returned a person. The viewer's no is now checked first
  and returns before the forced value is read.
- [x] **Route guards.** `/call` needs an accepted encounter, `/call/consent`
  needs a call that ended through the call screen, `/reveal` needs a stored
  mutual reveal. A direct link to the gate plus one click used to reach the
  reveal on a fresh store.
- [x] **Restart recovery is genuine.** The run id that addresses every graph
  thread is now durable, so a NEW process resumes an encounter opened by a
  previous one — including after a demo reset, which was the broken case.
  Tested by constructing new `SparkSession` objects, not by clearing a dict.

## Release gates

| Gate | Current status | Required before proceeding |
| --- | --- | --- |
| Recorded hackathon demo | **Ready** | All ten client milestones built; MockAdapter is the filming default. |
| Closed, consenting-device test | Blocked | Complete the pilot-integration items below. |
| Public pilot | Blocked | Complete all P0 and P1 items, privacy review, incident response and a launch rollback rehearsal. |
| Production launch | Blocked | Complete every section, including monitoring, operations, legal/privacy and load/security testing. |

## P0 — blockers for a closed pilot

### Finish the user journey

- [x] Implement `/onboarding` with consented profile extraction and no
  appearance/photo/height inputs.
- [x] Implement `/home`, `/reveal`, and `/lockins`. No route renders a
  milestone placeholder any more; `shell.test.tsx` asserts the stub list is
  empty.
- [ ] Expose actual lock-ins and continuity briefs from the API. `GET
  /api/lockins` and `GET /api/briefs` currently return empty arrays.
- [x] Build `HttpAdapter`, enable the `/api` Vite proxy, and prove the full UI
  path runs against FastAPI.
- [x] Build the Director panel and browser demo controls. The strip is behind
  `?demo=1` and every action is awaited, so a control cannot appear to work
  while silently failing.
- [x] An end-to-end test drives home → encounter → call → consent → reveal →
  lock-in through the real router and store (`screens.test.tsx`). It runs
  against `MockAdapter`; the HTTP path is covered separately by
  `tests/test_api.py` at the API boundary. **A real browser E2E harness
  (Playwright) is still not present** — jsdom cannot prove a genuine
  page refresh.

### Replace single-user simulation with a safe pilot identity model

- [ ] Choose a pilot identity provider and implement authentication. The API
  currently has no auth and defaults every request to one in-memory simulated
  user.
- [ ] Add per-user and per-encounter authorisation checks to every read and
  mutation; a caller must never fetch or answer another encounter.
- [ ] Persist users, encounters, consent records, blocks, lock-ins and brief
  provenance in a real datastore. The process-local session/index is lost on
  restart even though the graph checkpoint can survive.
- [ ] Make the consent ledger append-only in durable storage, with transaction
  semantics and an audit trail. Test concurrent/double submissions.
- [ ] Decide and implement the verification approach before inviting strangers.
  The onboarding Singpass screen is an explicitly simulated, data-free UI
  concept; `verification_tier` remains only a synthetic field.

### Real voice without weakening the invariants

- [ ] Implement a LiveKit (or equivalent) adapter *behind* `spark-voice` MCP;
  do not create a second call path outside the supervisor graph.
- [ ] Issue short-lived room tokens using opaque, per-encounter participant
  identities. Never expose user IDs, display names or metadata to the peer.
- [ ] Enforce audio-only rooms, no recording, two-participant maximum, and
  server-side room deletion at 180 seconds. Use token expiry as an independent
  backstop.
- [ ] Decide whether the clock starts when the first participant joins or both
  are connected; implement and test no-show, late-join and microphone-denial
  paths so they are indistinguishable to the other party.
- [ ] Test the complete call/reveal flow on at least three separate devices and
  networks with a forced decline, no-show and mutual-yes case.

### Privacy, safety and pilot authority

- [ ] Obtain explicit approval for any use of real names, voice, location,
  contact details or chat IDs. The current project rule is synthetic data only;
  a real-person pilot changes the risk profile.
- [ ] Publish participant consent, data-use, retention/deletion and withdrawal
  flows before collecting data. Set and justify the continuity-memory retention
  period; 90 days is currently an unvalidated placeholder.
- [ ] Define location minimisation: source, precision, retention, processing
  purpose, deletion, and proof that no live location/distance/place reaches a
  peer.
- [ ] Define a Guardian escalation and incident-response process, including a
  human owner, emergency limitations, reporting, blocking, evidence access and
  response-time targets.
- [ ] State clearly that text is screened but call audio is not. Add participant
  messaging, abuse reporting and post-incident review before a pilot.
- [ ] Conduct and document target-user interviews. The project's own pressure
  test remains open until at least one target user validates the problem.

## P1 — deployment platform and security

### AWS / AgentCore

- [ ] Choose direct-code or container deployment and add reproducible Spark
  deployment configuration. There is currently no Spark `Dockerfile`,
  `agentcore.json`, IaC, or deployment script; the `lab/` deployment is a
  training example, not Spark infrastructure.
- [ ] Create least-privilege IAM roles for runtime, deployment, memory,
  logging, model invocation, secrets and any tool integrations.
- [ ] Configure a non-production AWS account/environment, explicit region,
  budget alarms and mandatory resource tags.
- [ ] Create AgentCore Memory with per-user actor scoping, customer-managed KMS
  encryption, retention/deletion controls and access logging. AgentCore Memory
  persists long-term conversational information, so it cannot be treated as a
  drop-in replacement for an in-memory demo store.
- [ ] Configure the runtime network boundary: private subnets/security groups,
  VPC endpoints where needed, outbound allow-list and a threat-modelled
  connection path to LiveKit, notification and data services.
- [ ] Add deployment health/readiness checks, rollback, version promotion and a
  smoke test after deployment. If using a container runtime, satisfy AgentCore
  runtime requirements such as ARM64 compatibility and the expected invocation
  endpoint/port.

### API and web delivery

- [ ] Remove demo CORS (`allow_origins=["*"]`) and permit only the deployed web
  origin(s), with credential and header policy reviewed.
- [ ] Put the API behind authenticated HTTPS, rate limits, request-size limits,
  WAF/DDoS protections and structured error handling that does not leak state.
- [ ] Add CSRF protection where browser cookie authentication is used.
- [ ] Deploy the static web build to a managed host/CDN with HTTPS, cache policy,
  Content Security Policy, security headers and a custom error page.
- [ ] Move all secrets to a managed secret store; document rotation and prove
  secrets never appear in logs, OTEL attributes, browser bundles or CI output.
- [ ] Add an OpenAPI contract check and generated/contract-tested client types
  so Python and TypeScript cannot silently drift.

### Observability and operations

- [ ] Export OpenTelemetry to a durable collector/backend. Current traces are
  process-local `SimpleSpanProcessor`/collector data, suitable for the demo
  panel but not incident investigation.
- [ ] Create dashboards and alerts for availability, latency, error rate,
  consent-gate failures, identity/location leakage attempts, tool failures,
  cost, provider fallbacks and safety reports.
- [ ] Write runbooks for service degradation, model-provider outage, voice
  outage, stuck consent gate, data deletion request, abuse report and rollback.
- [ ] Add backups, restore tests, retention policies and disaster-recovery
  objectives for each persistent store.

## P1 — quality gates

- [ ] Run the evaluation on the chosen Bedrock deployment with current model
  prices and retain the raw report. The documented Bedrock run has not yet been
  performed; current results are deterministic or Groq-labelled.
- [ ] Resolve the product decision for the rematch cooldown using the sweep;
  the current 30-day default is intentionally not yet decided.
- [ ] Add API integration tests for auth, authorisation, concurrent consent,
  restart/recovery, rate limiting, CORS and error responses.
- [ ] Add browser E2E tests for every consent branch and the real adapter.
- [ ] Clear frontend test warnings: mock canvas correctly, replace the dynamic
  import warning, and wrap asynchronous state updates in `act(...)`.
- [ ] Add dependency, secret, SAST and licence scanning to CI; fail releases on
  high-severity findings.
- [ ] Run threat-model, penetration and privacy tests focused on identity,
  location, timing and consent-oracle leakage.
- [ ] Run capacity/load and chaos tests for concurrent calls, reconnects,
  provider failure, datastore failure and process restarts.

## P2 — launch evidence and product decisions

- [ ] Define pilot success/failure criteria, cohort size, stopping rules and
  owner for each metric. Keep the negative matching result visible rather than
  reframing it as evidence of predictive compatibility.
- [ ] Reconcile pricing with the one-encounter-per-day promise; do not sell
  “additional encounters” if the product position is depth over volume.
- [ ] Publish a transparent explanation of matching, fairness constraints,
  recommendation feedback, reporting/appeal and account deletion.
- [ ] Establish on-call coverage, support channels, incident communications and
  a participant offboarding process.
- [ ] Complete accessibility, mobile-device, slow-network and reduced-motion
  checks against the final deployed client.
- [ ] Record a deployment/rollback rehearsal and a real-device demo take before
  any public announcement.

## Evidence required to mark launch-ready

Before changing the decision at the top of this file to “ready”, attach:

1. CI links for backend, frontend, API contract, E2E, security and load suites.
2. Deployed environment URL(s), version/tag, infrastructure plan and rollback
   record.
3. Privacy/security sign-off, data inventory, retention policy and incident
   runbook.
4. A successful multi-device pilot report covering all consent outcomes.
5. Monitoring dashboard, alert test, backup/restore evidence and cost guardrail
   confirmation.

## Reference points

- `docs/PILOT.md` — current honest demo/pilot status and concrete LiveKit work.
- `docs/FRONTEND.md` — client definition of done and unfinished milestones.
- `spark/src/api/` — current demo-only HTTP layer.
- `spark/README.md` and `CLAUDE.md` — safety invariants and known limits.
- AWS recommends least privilege, durable observability and protected memory;
  AgentCore Memory supports encryption and persistent long-term information.
  See [AgentCore best practices](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/best-practices.html), [Memory encryption](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/storage-encryption.html), and [runtime deployment requirements](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-troubleshooting.html).
