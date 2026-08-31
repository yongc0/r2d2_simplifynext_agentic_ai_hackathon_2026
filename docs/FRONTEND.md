# FRONTEND.md — Spark demo client

Build specification for the Spark front end. Read alongside `CLAUDE.md` (working rules) and `docs/ARCHITECTURE.md` (system design).

---

## 1. What this front end is for

It has exactly two jobs, in this order:

1. **Carry the 5-minute submission video.** Every frame the judges see is this app. If it does not record well, nothing else matters.
2. **Make the agent layer visible.** Most hackathon UIs hide the AI behind a pretty screen. Ours shows the agents working, because "showcase your knowledge of Agentic AI" is a graded criterion.

It is **not** a production app. There is no real auth, no real telephony, no real location. Everything is driven by simulated data.

**Design goal in one line:** it should look like a shipped consumer product, not a hackathon prototype — calm, warm, confident, and nothing like a swipe app.

---

## 2. Stack

| Concern | Choice | Why |
|---|---|---|
| Build | **Vite + React 18 + TypeScript** | Fast, boring, no framework surprises during a demo |
| Styling | **Tailwind CSS** | No design-system dependency to break |
| State | **Zustand** | One store, minimal ceremony |
| Routing | **React Router** | Screens map to the encounter state machine |
| Animation | **Framer Motion** | Only where it earns it — see §7 |
| Icons | **lucide-react** | — |
| Data | **Adapter layer** — see §4 | Runs fully offline; swaps to the real backend with one env var |

No component library beyond Tailwind. No CSS-in-JS. No state library beyond Zustand.

```bash
npm create vite@latest web -- --template react-ts
cd web && npm i zustand react-router-dom framer-motion lucide-react
npm i -D tailwindcss @tailwindcss/vite
npm run dev
```

---

## 3. Layout: phone frame on desktop

The product is a phone app. The video is recorded on a desktop.

- Under `768px`: full-bleed, real mobile layout.
- At `768px` and above: render the app inside a **centred 390 × 844 device frame** (iPhone-ish, rounded 44px, subtle bezel and shadow) on a soft neutral backdrop.
- The **Director panel** (§8) docks to the right of the frame on desktop only. It is never part of the phone UI.

This one decision makes the recording look intentional rather than like a stretched mobile page.

---

## 4. Data adapter — build against mocks first

Everything goes through `src/api/adapter.ts`, which exports one interface with two implementations:

```ts
// src/api/types.ts  — must stay in step with src/schemas/ on the Python side

export type EncounterState =
  | 'IDLE' | 'WINDOW_OPEN' | 'NOTIFIED' | 'PENDING_ACCEPT'
  | 'CONNECTED' | 'CALL_ENDED' | 'PENDING_CONSENT'
  | 'REVEALED' | 'CLOSED' | 'ABANDONED';

export type Intent = 'partner_long' | 'partner_short' | 'friends';

export interface EncounterCard {
  encounterId: string;
  state: EncounterState;
  intent: Intent;
  // NOTHING identifying. No name, no photo, no age, no distance, no place.
  overlapHint: string;        // e.g. "Your paths crossed this afternoon"
  windowClosesAt: string;     // ISO
}

export interface RevealedPerson {
  personId: string;
  displayName: string;
  avatarSeed: string;         // generated illustration, never a real photo
  sharedInterests: string[];
}

export interface LockIn {
  lockInId: string;
  person: RevealedPerson;
  openedAt: string;
  lastContactAt: string | null;
  state: 'active' | 'quiet' | 'released';
}

export interface ContinuityBrief {
  lockInId: string;
  line: string;               // "Mei mentioned a certification exam on Thursday"
  suggestedAction: string;
  sourceEncounterId: string;
}

export interface AgentEvent {              // powers the Director panel
  ts: string;
  agent: 'onboarding' | 'match' | 'delivery' | 'continuity'
       | 'communication' | 'date' | 'guardian' | 'safety';
  action: string;
  detail: string;
  durationMs: number;
  tokens?: number;
  status: 'ok' | 'retry' | 'error';
}
```

- `MockAdapter` — deterministic, seeded, scripted. **Default.** The app must run with `npm run dev` and no backend at all.
- `HttpAdapter` — talks to the FastAPI layer. Enabled with `VITE_API=http`.

> **AMENDED DURING THE BUILD — four type drifts, resolved in `web/src/api/wire.ts`.**
> The draft above disagreed with `spark/src/schemas/` in four places. Each
> decision, with its reasoning, lives in that one file; overriding any of them is
> a change there and nowhere else.
>
> 1. **`Intent` values — the backend wins.** The draft spelled these
>    `partner_long` / `partner_short`; the pydantic enum is `partner_long_term` /
>    `partner_short_term`. A straight mismatch with no upside — `HttpAdapter`
>    would have failed to match, silently.
> 2. **`EncounterState` — deliberately two types.** The client keeps the ten
>    states above as `ClientState`; the backend's thirteen stay as the wire enum,
>    with one `mapWireState()` between them. `PROFILED`/`POOLED`/`SELECTED` are
>    backend-internal (the user sees nothing until `NOTIFIED`), `LOCKED_IN`/
>    `RELEASED` belong to the LockIn, and `IDLE`/`WINDOW_OPEN` are client-only.
> 3. **`EncounterCard` gains `handle`, `sharedInterests` and `callSeconds`.** A
>    pseudonymous handle is not an identity — it comes from a fixed word list and
>    is never derived from a name — so §9.2 permits it, and it gives two
>    strangers something to refer to for three minutes. Behind
>    `SHOW_HANDLE_PRE_REVEAL`, one line to reverse.
> 4. **`RevealedPerson.avatarSeed` / `sharedInterests` and all four
>    `ContinuityBrief` fields** have no backend counterpart. They are client
>    shapes; the mapping is in `wire.ts` and `spark/src/api/mapping.py`.

**Both adapters now exist.** `spark/src/api/` (`uv run -m src.api`) drives the
same supervisor graph the CLI drives, and `HttpAdapter` is verified against it
end to end. `MockAdapter` remains the DEFAULT and is what the video is filmed
against — the requirement above is that the demo exists without a backend, and
that stays true.

Build every screen against `MockAdapter`. Wire `HttpAdapter` last. If the backend is late, the demo still exists.

---

## 5. Screens

Routes map to the backend state machine so the two never drift.

### 5.1 `/onboarding` — verification concept + conversational intake

Begin with a three-step, explicitly simulated Singpass verification concept:
Spark explains the purpose, a disclosure shows the two confirmations it would
request, and a success screen hands off to profile intake. It must say on every
screen that no real Singpass connection exists. Render no login, credential or
identity-number field and make no external request. The concept confirms only
18+ eligibility and a one-way unique-account token; it does not set a real
verification tier.

Chat, not a form. The agent asks one thing at a time; the user replies in free text; extracted fields appear as **chips that fill in live** in a panel above the conversation.

When availability is unresolved, show all six valid backend time buckets as a
two-column choice grid: Early morning, Morning, Midday, Afternoon, Evening and
Night. Keep free text available, but never require the person to guess the
extractor's vocabulary.

That live extraction is the shot that sells the Onboarding Agent in three seconds. Animate each chip in as it is captured.

Ends with a mode selection: **Potential Partner** (long-term / short-term) or **Potential Friends**.

**Never render a height field, an appearance filter, or a photo upload.** These are deliberately excluded from the product.

### 5.1a `/profile` — what you told Spark

Onboarding is a conversation you have once; this is the same information as a
surface you can return to. A profile you can only set by re-running an intake
chat is a profile nobody corrects.

The rules from §5.1 still apply: intent is chosen from three options in a fixed
order with nothing preselected, and there is no height, appearance or photo
field — the interest vocabulary is the fixed list from `extract.ts`, so there is
nothing to type into either.

With no auth there is nobody to save a profile to, and the screen says so
rather than implying a durable account.

### 5.2 `/home` — the waiting state

Deliberately, almost aggressively empty. One line of copy and a countdown to the evening encounter window.

> Your encounter window opens at 9:00pm.
> `04:12:38`

Below: the lock-in list (§5.7) if any exist, and — only while it is missing — a
prompt to set up a profile, because that is the one thing that genuinely stops
the product working.

Nothing else. No feed, no browse, no activity. The emptiness is the product
argument — there is nothing here to scroll.

> **AMENDED DURING THE BUILD.** This section originally read "no profiles". That
> rule is about not BROWSING OTHER PEOPLE, and it stands: there is no discovery,
> no feed, and no list of strangers anywhere in the app. Reaching your OWN
> profile, lock-ins and plans is a different thing, and an app whose features
> cannot be reached cannot be demonstrated. See §5.9.

### 5.9 Navigation

Four destinations, in a bar at the bottom: **Home, Plans, Lock-ins, You.** There
is deliberately no fifth, and there will not be one that lists people you have
not met — `navigation.test.tsx` asserts the count and the absence.

**The bar is hidden on `/onboarding`, `/encounter*`, `/call*` and `/reveal`,**
and both reasons are product reasons rather than layout ones:

- Three minutes only works because there is nowhere else to be. A nav bar during
  a call is an escape hatch.
- The consent gate is two buttons and a genuinely uncertain wait. A third exit
  turns a decision into something you can wander away from — and the other
  person is waiting on it.

`HIDDEN_ON` is a list of route PREFIXES, so a nested route added later under
`/call` inherits the rule rather than quietly escaping it.

### 5.3 `/encounter` — the notification

Full-screen. The single most important visual in the video.

> **You crossed paths today.**
> Someone here might be worth three minutes.
> *Your paths crossed this afternoon.*
>
> `[ Accept ]`  `[ Not tonight ]`

Absolutely nothing identifying: no name, no photo, no age, no distance, no place name, no map, no "2 km away". A blurred silhouette is also forbidden — it implies an appearance.

On accept → `/encounter/waiting`, a quiet "waiting for the other person" state with a soft pulse, timing out gracefully.

### 5.4 `/call` — the three-minute call *(hero screen)*

- A large **circular countdown from 3:00**, drawn as an SVG ring that depletes.
- An **animated voice waveform** reacting to mock audio amplitude — this is what makes the screen read as a live call on video.
- Mute and speaker controls (visual only).
- Discreet **Guardian** affordance (§5.8).
- At `0:30` remaining, the ring shifts to a warmer tone. No alarm sound.
- At `0:00` the call ends automatically and routes to `/call/consent`. **There is no extend button** — the 180-second stop is a product invariant.

The Communication Agent's prompts, when the mock conversation stalls, appear as a **soft card sliding up from the bottom** — clearly a suggestion, never a takeover:

> *Suggested: you both mentioned living abroad — ask where.*

### 5.5 `/call/consent` — the decision

> **Would you like to connect?**
> `[ Yes ]`  `[ No ]`

Then a genuinely uncertain waiting state. Do not animate a hopeful outcome before it is known.

- **Both yes** → `/reveal`
- **Anything else** → a neutral close screen. **The copy must never reveal that the other person declined.** "That one is closed. Your next encounter is tomorrow at 9pm." Same screen, same wording, whether the user declined or the other person did.

### 5.6 `/reveal` — identity

The payoff. Names, generated avatar illustrations, shared interests. A restrained reveal animation — a fade and rise, not confetti. Then a single action: **Add to lock-ins**.

### 5.7 `/lockins` — the five slots

Five slots rendered as five slots, with empty ones visibly empty. Scarcity is the point and should be legible at a glance.

Each active lock-in shows a **Continuity brief**:

> **Mei** · connected 6 days ago
> *She mentioned a certification exam on Thursday.*
> `[ Ask how it went ]`

Quiet lock-ins get a distinct, non-guilting treatment. Released ones fade out rather than vanishing.

### 5.8 Guardian — the discreet exit

Available during a call and during any logged in-person meeting. A small, unlabelled affordance — recognisable to the user, unremarkable to an observer.

Triggering it produces a **plain incoming-call style interruption** giving the user a reason to step away, followed by a private check-in card.

**It must never imitate an iOS or Android system alert, a battery warning, or any OS-level chrome.** It is a safety feature, not a deception tool. Style it as clearly in-app.

---

## 6. The Director panel (desktop only)

A live agent trace beside the phone frame. This is what turns a nice UI into evidence of an agentic system, and no other team will have it.

Each `AgentEvent` streams in as a row:

```
21:00:02  match         selected candidate      412ms   1,240 tok   ✓
21:00:02  safety        screened notification    88ms               ✓
21:00:14  delivery      both accepted → connect  31ms               ✓
21:01:47  communication prompt (grounded)       380ms     610 tok   ✓
21:03:00  delivery      hard stop at 180s         4ms               ✓
21:03:12  continuity    lock-in opened           210ms     330 tok   ✓
```

- Colour-code by agent; keep it monospace and calm.
- Show a **running token cost** and **elapsed wall time** at the top — these are two of the six graded metrics, on screen, live.
- A collapsible detail row per event showing the rationale the agent returned.
- Toggle with `D`. Hidden by default so the phone can be filmed clean, then revealed.

---

## 7. Visual language

| Token | Value |
|---|---|
| Background | `#0F0D0E` (dark by default — records better and suits an evening product) |
| Surface | `#1A1719` |
| Accent | `#B03060` |
| Accent soft | `#E8A0B8` |
| Text | `#F5F0F1` / muted `#9A9094` |
| Radius | `20px` cards, `999px` buttons |
| Type | Inter or system stack. Generous sizes — this gets filmed and compressed |

**Motion rules.** Animate: the countdown ring, the waveform, chip extraction, the reveal, prompt cards sliding up. Do not animate: routine navigation, list rendering, hover states. Every animation ≤ 400ms. Respect `prefers-reduced-motion`.

**Tone of copy.** Plain, warm, short. Never coy, never gamified. No "🔥 3 day streak", no match percentages, no "hot singles". If a string sounds like a dating app, rewrite it.

---

## 8. Demo controls

Six weeks of continuity has to fit inside five minutes.

A dev-only control strip (hidden behind `?demo=1`):

- **Be someone else** — a persona picker, so a presenter can show two different
  people without restarting the server. `VITE_API=http` only: MockAdapter has
  one scripted pair, so the picker hides rather than offering a single option
  that changes nothing.
- **New encounter** — another one, now. Implemented as "let it be tomorrow",
  because one encounter per person per day IS the product and the id derives
  from the day. Keeps lock-ins and Date Studio memory, so the recommender can be
  shown improving across encounters; `Reset` is what clears those.
- **Skip to encounter window** — bypass the countdown
- **Advance one day / one week** — drives the Continuity Agent forward
- **Force outcome** — both-yes / one-no / no-show, for filming each branch
- **Reset** — deterministic seed, so takes are repeatable

Every state must be reachable in under three clicks. You will re-record more times than you expect.

---

## 9. UI invariants

These mirror the backend invariants in `CLAUDE.md`. A front end can break them by accident — a placeholder that says "2 km away" undoes the entire safety argument.

1. **Never render a distance, coordinate, place name, or map.** Overlap is described in words only ("this afternoon"), never located.
2. **Never render identity before mutual consent** — no name, no photo, no age, no blurred silhouette, no initial.
3. **A decline produces an identical screen either way.** Same copy, same timing, same everything, whether the user declined or the other person did. Do not vary the delay.
4. **No extend-the-call control.** The 180-second stop is absolute.
5. **No height, appearance, or photo-based filtering anywhere in onboarding or preferences.**
6. **Guardian never imitates system chrome.**
7. **Avatars are generated illustrations.** Never a stock photo of a real person, at any point, including placeholders.

Add a test in `web/src/__tests__/invariants.test.tsx` asserting that pre-reveal screens render no identity fields and no distance strings.

---

## 10. Definition of done

- [ ] `npm run dev` works with **no backend running** and no keys
- [ ] The full path is clickable: onboarding → home → encounter → call → consent → reveal → lock-in → continuity brief
- [ ] All three consent outcomes are reachable and visually correct
- [ ] Director panel streams agent events with live token and time counters
- [ ] Demo controls reach any state in ≤3 clicks and reset deterministically
- [ ] Renders in a device frame ≥768px, full-bleed below
- [ ] Every §9 invariant holds, with tests for 1, 2 and 3
- [ ] `VITE_API=http` switches to the real backend without touching component code
- [ ] Records cleanly at 1080p — no layout shift, no flash of unstyled content, no scrollbars in frame

---

## 11. Build order

1. ✅ Shell: device frame, routing, Zustand store, Tailwind tokens
2. ✅ `MockAdapter` with a full scripted encounter
3. ✅ `/call` — the hero screen, first, because everything else is judged against it
4. ✅ `/encounter` and `/call/consent`, including all three outcomes
5. ✅ `/onboarding` with a simulated Singpass verification concept and live chip extraction — no credentials are collected; chips animate in per turn; intent is asked, never inferred
6. ✅ `/reveal` and `/lockins` with continuity briefs — plus `/home`, which this list never named
7. ✅ Director panel — toggle `D`, live token + elapsed, real OTEL spans on `VITE_API=http`
8. ✅ Demo controls — behind `?demo=1`, outside the phone frame, every action awaited
9. ✅ Guardian — in-app reminder then a private check-in; never system chrome
10. ✅ `HttpAdapter` — `VITE_API=http`, verified end to end through the Vite proxy

**Status: 10 of 10.** Every milestone is built, and no route renders a
placeholder. `/home` was never in the list above — a gap in this build order —
and shipped with milestone 6, since §5.2 puts the lock-in list on it.

Tests: **220 passing, no warnings.** All seven §9 invariants have a screen-level
test, indexed and asserted in `invariants.test.tsx` so deleting one to make a
feature pass fails loudly. The fixtures `MockAdapter` shares with the Python
agents — the onboarding keyword lists and the call transcript — are held in step
by `spark/tests/test_wire_contract.py`, which reads the TypeScript as text.

**If you run out of time, cut in reverse order — but never cut the Director panel.** It is worth more to the technical score than Guardian and the real adapter combined.
