# Spark

One anonymous three-minute voice call a day, with one person whose path crossed
yours today. Identity is revealed only if you both say yes afterwards. The system
then stays with the connection for weeks.

Built for the SimplifyNext Agentic AI Hackathon 2026.

**Everything is simulated.** No real users, no real location data, no real
telephony, and no real Singpass integration. Onboarding includes a clearly
labelled Singpass verification concept that accepts no credentials or identity
data. The voice bridge is a mock and the world is 60 synthetic personas. This
is a demonstration of an agentic system, not a service anyone
should point at real people — see [DEPLOYMENT_READINESS.md](DEPLOYMENT_READINESS.md),
which says so in more detail and lists what a real pilot would require.

---

## Quick start

Two processes. Neither needs an API key.

```bash
# the demo client — works with NO backend at all
cd web
npm install
npm run dev                  # http://localhost:5173

# the API, if you want the real graph behind it
cd spark
uv sync
uv run -m src.api            # http://127.0.0.1:8000
VITE_API=http npm run dev    # then point the client at it
```

`MockAdapter` is the default on purpose: a fresh clone with no keys and no
backend still runs the whole experience. That is what the submission video is
filmed against.

```bash
cd spark && uv run pytest    # 329 passed, 1 skipped
cd web   && npm test         # 231 passed
```

### Real venues for the date planner

The planner names real places, with addresses, opening hours and walking times.
That data is **OpenStreetMap's**, fetched once and committed — never a live API
call, so the demo cannot fail because a public server rate-limited us mid-take,
and the same plan comes out on every run.

```bash
cd spark
uv run python scripts/fetch_venues.py           # needs network, once
uv run python scripts/export_venues_for_web.py  # bundles a slice for the offline client
```

Until those have run, **the planner says it has no venue data and suggests
nothing**. That is deliberate. A fabricated address is a real person standing
outside a building that was never there, so an unavailable state is the correct
output, not a bug to paper over.

These are real businesses that **Spark has not visited or evaluated**, and
nothing in the product implies otherwise. Any screen showing them credits
"© OpenStreetMap contributors", which is a licence condition rather than a
courtesy.

No Google Maps API key is used anywhere, and none is needed. The map is drawn
from the coordinates — so it works offline like the rest of the client — and the
per-stop **Navigate** buttons open real Google Maps directions through
`maps/dir/?api=1`, a documented public URL that takes no credential. There is
therefore no key in the bundle to leak.

---

## What is here

| Path | What it is |
| --- | --- |
| [`spark/src/graph/`](spark/src/graph/) | The LangGraph supervisor. Both consent gates are `interrupt()` calls |
| [`spark/src/agents/`](spark/src/agents/) | One module per agent, each naming the organisers' agent class it belongs to |
| [`spark/src/mcp/`](spark/src/mcp/) | Seven MCP servers — every external capability is a tool, not a function call |
| [`spark/src/memory/`](spark/src/memory/) | Durable preferences, plans, and the private post-date reflections |
| [`spark/scripts/`](spark/scripts/) | One-off venue fetch from OpenStreetMap, and the bundle for the offline client |
| [`spark/src/safety/`](spark/src/safety/) | Consent, the reveal, the guardrails. Ordinary Python with tests, no model |
| [`spark/eval/`](spark/eval/) | The three-arm evaluation: Spark vs random vs similarity |
| [`web/`](web/) | The demo client. Vite + React + Tailwind |
| [`docs/`](docs/) | [ARCHITECTURE](ARCHITECTURE.md) · [FRONTEND](docs/FRONTEND.md) · [PILOT](docs/PILOT.md) |
| [`lab/`](lab/) | The workshop lab this repository started from — see the bottom of this file |

---

## The six invariants

These are the product. Each has a test in
[`spark/tests/test_consent.py`](spark/tests/test_consent.py), and none of them
is enforced by a model.

1. **No identity, photo, or number before both parties say yes after the call.**
2. **A decline emits no observable signal** — no count, no timing difference,
   nothing inferable.
3. **No distance, place name, coordinate, or map is ever rendered.** Overlap is a
   coarse cell and a time bucket, historical only.
4. **The call stops at 180 seconds.** Either person may leave sooner; nothing can
   extend it.
5. **Consent events are append-only** and never joined into anything user-facing.
6. **No model decides any of the above.**

The client mirrors them as seven UI invariants ([FRONTEND.md §9](docs/FRONTEND.md)),
each with a screen-level test — because a front end can undo the whole safety
argument with a placeholder that reads "2 km away".

---

## What we found, and reported anyway

**The pre-registered result is negative.** The Match Agent does not beat random
assignment on mutual connect rate: **Spark 12.6% vs random 12.6%, p = 0.97.** It
was pre-registered before the run and it is reported as it stands. The encounter
format would still be the product; the ranking is not doing the work we hoped.

**The graded numbers are not yet from Bedrock.** Routing and dependencies are in
place, but no AWS credentials exist on the build machine, so every figure in the
report is Groq-derived or deterministic and the report labels it that way.

**Zero user interviews have been conducted.** The design rests on desk research.

---

## The lab

This repository began as the hackathon's teaching lab, which is still here under
[`lab/`](lab/) — six sections from a raw LLM call through LangGraph to Bedrock
AgentCore. It is the organisers' material and is unrelated to Spark's code; if
you are reviewing the submission, everything you want is in `spark/` and `web/`.

```bash
cd lab && uv sync && uv run 00_check_env.py
```
