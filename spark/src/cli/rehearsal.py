"""A simulated pilot — the whole product, driven as if two people were using it.

    uv run -m src.cli.rehearsal
    uv run -m src.cli.rehearsal --branch declined
    uv run -m src.cli.rehearsal --branch guardian

WHAT THIS IS

Every step below is a real HTTP request to the real FastAPI app, driving the
real supervisor graph. The consent gates are the same LangGraph `interrupt()`
calls the evaluation drives. Nothing is stubbed for the sake of the transcript.

WHAT IT IS NOT, AND WHY THAT MATTERS

It is not two people. There is no auth (docs/PILOT.md), so the server cannot
tell two browsers apart, and the second person is played by the simulator —
`peer_yes` is a parameter, not somebody's decision. Every line the other party
"says" below is marked `[sim]`.

That distinction is the whole reason this file prints it. A rehearsal that
reads like a real pilot is worse than no rehearsal: it invites the claim that
two people have used this, and nobody has.
"""

from __future__ import annotations

import argparse
import sys

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.cli._console import rule, use_utf8

#: What the simulated other party does at the reveal gate, per branch.
BRANCHES = ("mutual", "declined", "no_response", "guardian")


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(
        description="Walk the whole product as a simulated pilot session."
    )
    parser.add_argument(
        "--branch", choices=BRANCHES, default="mutual",
        help="what the simulated other party does, or 'guardian' to raise a concern",
    )
    args = parser.parse_args()

    client = TestClient(create_app())
    client.post("/api/demo/reset")

    print(rule("SPARK — SIMULATED PILOT SESSION"))
    _preamble(client, args.branch)

    encounter_id = _evening_one(client, args.branch)
    if encounter_id is None:
        return 1

    if args.branch == "guardian":
        _guardian(client, encounter_id)
        _closed_out(client)
        _epilogue(args.branch)
        return 0

    revealed = _the_gate(client, encounter_id, args.branch)
    if not revealed:
        _closed_out(client)
        _epilogue(args.branch)
        return 0

    lockin_id = _the_weeks_after(client)
    if lockin_id:
        _date_studio(client, lockin_id)
    _epilogue(args.branch)
    return 0


# ---------------------------------------------------------------------------


def _preamble(client: TestClient, branch: str) -> None:
    health = client.get("/api/health").json()
    print()
    print("  Everything below is a real request to the real graph.")
    print("  Lines marked [sim] are the SIMULATOR playing the other person.")
    print("  There is no auth, so there is no second person. Nobody has used this.")
    print()
    print(f"  provider   {health['provider']}")
    print(f"  world      {health['worldUsers']} synthetic personas")
    print(f"  call       {health['callSeconds']}s hard stop")
    print(f"  branch     {branch}")
    print()


def _evening_one(client: TestClient, branch: str) -> str | None:
    print(rule("9:00pm — the window opens", "-"))
    response = client.post("/api/encounters")
    if response.status_code == 409:
        print("\n  A quiet day. Nobody eligible crossed their path.")
        print("  This is a normal outcome, not a failure.\n")
        return None

    card = response.json()
    print()
    print("  ON THE PHONE:")
    print("      You crossed paths today.")
    print("      Someone here might be worth three minutes.")
    print(f"      {card['overlapHint']}")
    print()
    print("  What the card carries, in full:")
    print(f"      handle          {card['handle']}")
    print(f"      shared          {', '.join(card['sharedInterests']) or '—'}")
    print(f"      call length     {card['callSeconds']}s")
    print("      name            (absent — there is no field for one)")
    print("      place/distance  (absent — there is no field for one)")
    print()

    if branch != "mutual" and branch != "guardian":
        client.post(
            "/api/demo/force-outcome", json={"outcome": branch}
        )
        print(f"  [sim] the other party will answer the reveal gate: {branch}")

    print("  YOU: Accept")
    print("  [sim] they accept too")
    client.post(f"/api/encounters/{card['encounterId']}/respond", json={"accept": True})
    print()
    print("  The bridge opens. Both legs anonymous, hard stop armed at 180s.")
    print()
    return card["encounterId"]


def _guardian(client: TestClient, encounter_id: str) -> None:
    print(rule("0:40 into the call — something feels off", "-"))
    print()
    print("  YOU: press the discreet dot")
    print()
    print("  ON THE PHONE:")
    print("      Spark · your reminder")
    print("      Your reminder: you said you needed to leave by now.")
    print("      [ Step away now ]  [ Not now ]")
    print()
    print("  Nothing here imitates an OS alert. It is the product's own surface.")
    print()
    print("  YOU: Step away now  ->  'Something felt off'")

    result = client.post(
        f"/api/encounters/{encounter_id}/guardian/check-in",
        json={"allRight": False},
    ).json()
    print()
    print(f"  SERVER: {result['message']}")
    print()
    print("  Now the important part — the encounter is closed ON THE SERVER.")
    attempt = client.post(
        f"/api/encounters/{encounter_id}/consent", json={"yes": True}
    ).json()
    print(f"      a later 'yes' at the gate returns: {attempt}")
    print("      no identity, no lock-in, and date planning is refused.")
    print()
    print("  [sim] the other party is told nothing. From their side this is")
    print("        a decline or a no-show — indistinguishable, as required.")
    print()


def _the_gate(client: TestClient, encounter_id: str, branch: str) -> bool:
    print(rule("3:00 — the call ends on its own", "-"))
    print()
    print("  Nobody hung up. The time ran out.")
    print()
    print("  ON THE PHONE:")
    print("      Would you like to connect?")
    print("      We will only tell either of you if you both say yes.")
    print()
    print("  YOU: Yes")

    outcome = client.post(
        f"/api/encounters/{encounter_id}/consent", json={"yes": True}
    ).json()

    if outcome["outcome"] != "mutual":
        print(f"  [sim] the other party: {branch}")
        print()
        print("  ON THE PHONE:")
        print("      That one is closed.")
        print("      Your next encounter is tomorrow at 9pm.")
        print()
        print("  The screen is byte-identical whichever of you said no,")
        print("  and the wait is the same length either way.")
        print()
        return False

    person = outcome["person"]
    print("  [sim] the other party: Yes")
    print()
    print("  ON THE PHONE:")
    print("      You both said yes")
    print(f"      {person['displayName']}")
    print("      You spoke without knowing that.")
    print(f"      shared: {', '.join(person['sharedInterests']) or '—'}")
    print()
    print("  This is the only screen in the product that may render a name,")
    print("  and the only path that produces one.")
    print()
    return True


def _closed_out(client: TestClient) -> None:
    lockins = client.get("/api/lockins").json()
    print(f"  lock-ins opened: {len(lockins)}")
    print()


def _the_weeks_after(client: TestClient) -> str | None:
    print(rule("The weeks after", "-"))
    lockins = client.get("/api/lockins").json()
    if not lockins:
        print("\n  No lock-in.\n")
        return None

    lockin = lockins[0]
    briefs = client.get("/api/briefs").json()
    print()
    print(f"  Lock-in opened with {lockin['person']['displayName']}  ({lockin['state']})")
    if briefs:
        print(f"      brief:  {briefs[0]['line']}")
        print(f"      action: {briefs[0]['suggestedAction']}")
    print()
    print("  [sim] five weeks pass")
    client.post("/api/demo/advance-days?days=35")

    later = client.get("/api/briefs").json()
    state = client.get("/api/lockins").json()[0]["state"]
    print()
    if later:
        print(f"      brief:  {later[0]['line']}")
        print(f"      action: {later[0]['suggestedAction']}   <- week one said 'Ask how it went'")
    print(f"      state:  {state}   <- quiet, and never nagged about it")
    print()
    return lockin["lockInId"]


def _date_studio(client: TestClient, lockin_id: str) -> None:
    print(rule("Date Studio — planning something", "-"))
    prefs = client.get(f"/api/lockins/{lockin_id}/date-preferences").json()
    print()
    print(f"  Times you are BOTH free: {', '.join(prefs['sharedBuckets']) or '—'}")
    print("  YOU: budget = free, energy = low, and tick 'Remember this'")
    print()

    first = client.post(
        f"/api/lockins/{lockin_id}/date-plans",
        json={"budget": "free", "energy": "low", "remember": True},
    ).json()
    _print_plans(first)

    if not first["paths"]:
        return

    rejected = first["paths"][0]
    print(f"  YOU: 'Not for us' on the {rejected['shape']} plan  ->  reason: too long")
    client.post(
        f"/api/date-plans/{rejected['pathId']}/feedback",
        json={"action": "rejected", "reasons": ["too_long"]},
    )
    print()

    second = client.post(
        f"/api/lockins/{lockin_id}/date-plans",
        json={"budget": "free", "energy": "low"},
    ).json()
    print("  Generate again:")
    _print_plans(second)

    changed = [p["pathId"] for p in first["paths"]] != [
        p["pathId"] for p in second["paths"]
    ]
    print(f"  Ranking changed: {changed}")
    print("  Not a retrained model — a re-rank over rows you can read:")
    print()

    for item in client.get(f"/api/date-memory?lockInId={lockin_id}").json():
        told = "you told us" if item["source"] == "explicit" else "we noticed"
        scope = "this connection only" if item["scope"] == "lockin" else "everywhere"
        print(
            f"      {item['dimension']:<9} {item['value']:<12} "
            f"{told:<12} conf {item['confidence']:<5} {scope}"
        )
    print()
    print("  Every line above can be corrected or deleted by the person it is about.")
    print()


def _print_plans(plan: dict) -> None:
    if not plan["paths"]:
        print(f"      (none — {plan['note']})")
        print()
        return
    for path in plan["paths"]:
        partner = any(s["isCommercialPartner"] for s in path["stops"])
        label = "  [contains a Spark partner venue]" if partner else ""
        print(f"      [{path['shape']:<5}] {path['headline']}{label}")
        print(f"              {path['rationale']}")
    print()


def _epilogue(branch: str) -> None:
    print(rule("WHAT THIS RUN DID AND DID NOT SHOW"))
    print()
    print("  Real:      the graph, both consent gates, the guardrails, the")
    print("             agents, the memory, and every refusal above.")
    print()
    print("  Simulated: the other person. There is no auth, so the server")
    print("             cannot tell two browsers apart — `peer_yes` is a")
    print("             parameter. Nobody has used this product.")
    print()
    print("  Also not real: the voice bridge (no audio), the venues (kinds of")
    print("             place, none of them exist), and the personas.")
    print()
    print("  Zero user interviews have been conducted.")
    print()
    print(rule())
    return None


if __name__ == "__main__":
    sys.exit(main())
