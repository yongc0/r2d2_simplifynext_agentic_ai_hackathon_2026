"""The ten numbers this project is judged on.

Six the organisers named (docs/ARCHITECTURE.md §17):

  1  schema validation pass rate     does another system get a usable output?
  2  tool-call success rate          does the agent reach for the right hands?
  3  loop discipline                 converging, or circling?
  4  token cost per run              what does one answer actually cost?
  5  task completion rate            did it carry the job to the end?
  6  answer fidelity                 right, as well as plausible?

Four of our own (§18), because the six above do not measure what would sink
this product:

  anonymity leakage rate       target zero. Non-negotiable.
  encounter distribution Gini  if a minority get most encounters we have
                               rebuilt the platform we set out to replace.
  guardrail false-negative     harmful content that got through. False
                               negatives matter far more than false positives.
  cost per successful connection   the number that decides whether this works
                               as a business.

Every record carries the provider that produced it, so a deterministic-policy
run can never be reported as a model run.
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from src.config import SETTINGS, Role


@dataclass
class Rate:
    """A hit/total counter that knows how to describe itself."""

    label: str
    hits: int = 0
    total: int = 0

    def record(self, hit: bool) -> None:
        self.total += 1
        self.hits += 1 if hit else 0

    @property
    def rate(self) -> float | None:
        return None if self.total == 0 else self.hits / self.total

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "hits": self.hits, "total": self.total, "rate": self.rate}


@dataclass
class Failure:
    """A failure worth naming in the report.

    The organisers ask explicitly for the failures to be logged, not just the
    success rate, and for errors to be *actionable for business users* — so
    `detail` is a sentence, never a code.
    """

    where: str
    detail: str


@dataclass
class TokenUsage:
    provider: str = "none"
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    calls: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def gini(counts: list[int]) -> float:
    """Gini coefficient of a distribution. 0 = perfectly even, 1 = one winner.

    Standard formula on the sorted values. Users with zero encounters are part
    of the distribution and must be included — dropping them would flatter the
    number, which is precisely the failure this metric exists to catch.
    """
    if not counts:
        return 0.0
    values = sorted(counts)
    n = len(values)
    total = sum(values)
    if total == 0:
        return 0.0
    weighted = sum((i + 1) * v for i, v in enumerate(values))
    return (2 * weighted) / (n * total) - (n + 1) / n


@dataclass
class MetricsRegistry:
    """One object, one process. Agents call `record_*`; nothing writes fields.

    Not thread-safe by accident — the lock is here because the simulation may
    fan a day's encounters out across threads and a lost increment would show
    up as a suspiciously good tool-call success rate.
    """

    # --- the organisers' six -------------------------------------------
    schema_validation: Rate = field(default_factory=lambda: Rate("schema validation pass rate"))
    tool_calls: Rate = field(default_factory=lambda: Rate("tool-call success rate"))
    task_completion: Rate = field(default_factory=lambda: Rate("task completion rate"))
    answer_fidelity: Rate = field(default_factory=lambda: Rate("answer fidelity"))

    #: loop discipline: iterations observed per agent run, and cap hits
    loop_iterations: list[int] = field(default_factory=list)
    loop_cap_hits: Rate = field(default_factory=lambda: Rate("runs reaching the loop cap"))

    #: token cost, split by tier so the report can say what each one cost
    tokens: dict[str, TokenUsage] = field(default_factory=dict)

    # --- our four ------------------------------------------------------
    anonymity_leaks: Rate = field(default_factory=lambda: Rate("anonymity leakage rate"))
    guardrail_false_negatives: Rate = field(
        default_factory=lambda: Rate("guardrail false-negative rate")
    )
    encounters_per_user: Counter = field(default_factory=Counter)
    mutual_connections: int = 0

    # --- diagnostics ---------------------------------------------------
    failures: list[Failure] = field(default_factory=list)
    schema_failures: list[Failure] = field(default_factory=list)
    #: Decisions that fell back to the deterministic policy because the model
    #: call failed or the run's model budget was exhausted. Reported, never
    #: hidden: CLAUDE.md forbids silently capping anything in the evaluation.
    llm_fallbacks: list[Failure] = field(default_factory=list)
    llm_calls_attempted: int = 0
    llm_calls_succeeded: int = 0

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # -------------------------------------------------------------------
    # Recording
    # -------------------------------------------------------------------

    def record_schema(self, agent: str, ok: bool, detail: str = "") -> None:
        """Metric 1. `ok` means it validated on the FIRST attempt — a retry
        that succeeds is still a miss, or the metric measures our retry loop
        instead of the model."""
        with self._lock:
            self.schema_validation.record(ok)
            if not ok:
                self.schema_failures.append(Failure(agent, detail or "validation failed"))

    def record_tool_call(self, server: str, tool: str, ok: bool, detail: str = "") -> None:
        """Metric 2. Every MCP call lands here, including the ones that failed
        and were retried successfully."""
        with self._lock:
            self.tool_calls.record(ok)
            if not ok:
                self.failures.append(Failure(f"{server}.{tool}", detail))

    def record_loop(self, agent: str, iterations: int, cap: int) -> None:
        """Metric 3. Both halves: how many iterations, and did it hit the cap."""
        with self._lock:
            self.loop_iterations.append(iterations)
            hit = iterations >= cap
            self.loop_cap_hits.record(hit)
            if hit:
                self.failures.append(
                    Failure(
                        agent,
                        f"reasoning loop reached the cap of {cap} iterations without "
                        "converging; the deterministic fallback decided this one",
                    )
                )

    def record_tokens(
        self,
        role: Role,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_creation: int = 0,
    ) -> None:
        """Metric 4. Input, output, cache read and cache creation — all four,
        because the cache columns are where a real bill differs from a naive
        estimate."""
        with self._lock:
            usage = self.tokens.setdefault(role, TokenUsage())
            usage.provider = provider
            usage.model = model
            usage.input_tokens += input_tokens
            usage.output_tokens += output_tokens
            usage.cache_read_tokens += cache_read
            usage.cache_creation_tokens += cache_creation
            usage.calls += 1
            usage.cost_usd += SETTINGS.pricing(role).cost(input_tokens, output_tokens)

    def record_task_completion(self, reached_gate: bool, detail: str = "") -> None:
        """Metric 5. Completion means *reaching* the human consent gate with no
        manual intervention — not passing it. A metric that counted passing
        would punish users for declining, which is behaving normally."""
        with self._lock:
            self.task_completion.record(reached_gate)
            if not reached_gate and detail:
                self.failures.append(Failure("encounter", detail))

    def record_fidelity(self, grounded: bool, detail: str = "") -> None:
        """Metric 6. For the Communication Agent: was the prompt grounded in
        something both people actually said?"""
        with self._lock:
            self.answer_fidelity.record(grounded)
            if not grounded and detail:
                self.failures.append(Failure("communication", detail))

    def record_anonymity_check(self, leaked: bool, detail: str = "") -> None:
        """Ours. Target zero. Every string rendered to any user is checked."""
        with self._lock:
            self.anonymity_leaks.record(leaked)
            if leaked:
                self.failures.append(Failure("anonymity", detail))

    def record_guardrail_case(self, harmful: bool, blocked: bool, detail: str = "") -> None:
        """Ours. A false negative is harmful content that was NOT blocked.

        Only harmful cases move this rate; benign cases are counted elsewhere
        so a large benign set cannot dilute the number that matters.
        """
        if not harmful:
            return
        with self._lock:
            self.guardrail_false_negatives.record(not blocked)
            if not blocked:
                self.failures.append(Failure("guardrail", detail))

    def record_encounter_for(self, *user_ids: str) -> None:
        """Ours. Feeds the distribution Gini."""
        with self._lock:
            for user_id in user_ids:
                self.encounters_per_user[user_id] += 1

    def record_mutual_connection(self) -> None:
        with self._lock:
            self.mutual_connections += 1

    def record_llm_attempt(self, ok: bool, detail: str = "") -> None:
        with self._lock:
            self.llm_calls_attempted += 1
            if ok:
                self.llm_calls_succeeded += 1
            elif detail:
                self.llm_fallbacks.append(Failure("model", detail))

    def record_llm_fallback(self, reason: str) -> None:
        """A decision the deterministic policy made because the model was not
        used. Counted separately from a failure — being over budget is a
        choice, not a fault — but reported either way."""
        with self._lock:
            self.llm_fallbacks.append(Failure("budget", reason))

    # -------------------------------------------------------------------
    # Derived
    # -------------------------------------------------------------------

    @property
    def total_cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.tokens.values())

    @property
    def total_tokens(self) -> int:
        return sum(u.total_tokens for u in self.tokens.values())

    @property
    def mean_loop_iterations(self) -> float | None:
        if not self.loop_iterations:
            return None
        return sum(self.loop_iterations) / len(self.loop_iterations)

    @property
    def encounter_gini(self) -> float:
        return gini(list(self.encounters_per_user.values()))

    def cost_per_connection(self) -> float | None:
        if self.mutual_connections == 0:
            return None
        return self.total_cost_usd / self.mutual_connections

    def reset(self) -> None:
        """Tests and each evaluation arm start from zero."""
        with self._lock:
            self.schema_validation = Rate("schema validation pass rate")
            self.tool_calls = Rate("tool-call success rate")
            self.task_completion = Rate("task completion rate")
            self.answer_fidelity = Rate("answer fidelity")
            self.loop_iterations = []
            self.loop_cap_hits = Rate("runs reaching the loop cap")
            self.tokens = {}
            self.anonymity_leaks = Rate("anonymity leakage rate")
            self.guardrail_false_negatives = Rate("guardrail false-negative rate")
            self.encounters_per_user = Counter()
            self.mutual_connections = 0
            self.failures = []
            self.schema_failures = []
            self.llm_fallbacks = []
            self.llm_calls_attempted = 0
            self.llm_calls_succeeded = 0

    def snapshot(self) -> dict[str, Any]:
        """A plain dict for the report and for JSON output."""
        with self._lock:
            return {
                "provider": SETTINGS.model.provider,
                "schema_validation": self.schema_validation.as_dict(),
                "tool_calls": self.tool_calls.as_dict(),
                "task_completion": self.task_completion.as_dict(),
                "answer_fidelity": self.answer_fidelity.as_dict(),
                "loop": {
                    "cap": SETTINGS.loop.max_iterations,
                    "mean_iterations": self.mean_loop_iterations,
                    "runs": len(self.loop_iterations),
                    "cap_hit_rate": self.loop_cap_hits.rate,
                },
                "tokens": {
                    role: {
                        "provider": u.provider,
                        "model": u.model,
                        "calls": u.calls,
                        "input": u.input_tokens,
                        "output": u.output_tokens,
                        "cache_read": u.cache_read_tokens,
                        "cache_creation": u.cache_creation_tokens,
                        "cost_usd": u.cost_usd,
                    }
                    for role, u in self.tokens.items()
                },
                "total_cost_usd": self.total_cost_usd,
                "anonymity_leakage": self.anonymity_leaks.as_dict(),
                "guardrail_false_negative": self.guardrail_false_negatives.as_dict(),
                "encounter_gini": self.encounter_gini,
                "users_with_encounters": len(self.encounters_per_user),
                "mutual_connections": self.mutual_connections,
                "cost_per_connection_usd": self.cost_per_connection(),
                "llm_calls": {
                    "attempted": self.llm_calls_attempted,
                    "succeeded": self.llm_calls_succeeded,
                    "fallbacks": len(self.llm_fallbacks),
                },
                "failures": [f.__dict__ for f in self.failures[:50]],
                "failures_total": len(self.failures),
                "schema_failures": [f.__dict__ for f in self.schema_failures[:20]],
                "schema_failures_total": len(self.schema_failures),
            }


#: Process-wide. Import this; do not build another.
METRICS = MetricsRegistry()
