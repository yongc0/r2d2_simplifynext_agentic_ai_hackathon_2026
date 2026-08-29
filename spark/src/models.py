"""The model layer. One factory, one call, one place the provider is named.

Switching provider is one line — `SPARK_LLM_PROVIDER` in `.env` — and no agent
module mentions Groq or Bedrock. That is the same shape as the teaching lab's
`_common.py`, and for the same reason: the agent written on Day 1 is the agent
that runs on Bedrock on Day 2.

`structured_call` is the only way an agent talks to a model, and it does four
things every such call must do:

  asks for a **pydantic schema**, never free text;
  records whether it validated **on the first attempt** (metric 1);
  records input, output and cache tokens, and the cost (metric 4);
  returns `None` rather than raising, so the caller falls back to its
  deterministic policy and the encounter still completes.

That last one is the difference between a demo and a system. A model outage
must degrade the *quality* of a selection, never the availability of the daily
encounter.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from src.config import SETTINGS, Role
from src.telemetry.metrics import METRICS
from src.telemetry.trace import span

T = TypeVar("T", bound=BaseModel)


class ModelUnavailable(RuntimeError):
    """The configured provider cannot be reached at all.

    Raised only from the factory, and only when the cause is a setup problem a
    person can fix — a missing key, an unknown provider. Per-call failures are
    not this; they return `None` and are counted.
    """


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


@dataclass
class ModelBudget:
    """A cap on real model calls for one run.

    A six-week simulation over 200 personas asks for thousands of judgement
    calls. On a free tier that is hours of wall-clock and a rate-limit wall; on
    Bedrock it is a bill. So a run may bound how many decisions the model makes
    — and when it does, every decision that fell back to the deterministic
    policy is counted and printed in the report.

    CLAUDE.md: *do not silently truncate, sample, or cap anything in the
    evaluation. If coverage is bounded, log what was dropped.* This class is
    how that promise is kept, rather than a comment saying it is.
    """

    limit: int
    used: int = 0
    _lock: threading.Lock = None                        # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.used >= self.limit:
                return False
            self.used += 1
            return True

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def reset(self, limit: int | None = None) -> None:
        with self._lock:
            self.used = 0
            if limit is not None:
                self.limit = limit


#: The run-wide budget. `src/cli/simulate.py` sets the limit.
BUDGET = ModelBudget(limit=SETTINGS.sim.llm_call_budget)


@dataclass
class CircuitBreaker:
    """Stop calling a provider that has failed repeatedly.

    Without this, a provider that starts rate-limiting turns every remaining
    decision in the run into a timeout plus two backoff retries. A six-week
    simulation then takes an hour instead of a minute, and each of those
    minutes buys nothing — the deterministic policy was going to decide anyway.

    Opening the breaker is not hiding the failure. It is recorded, and the
    report prints how many decisions the fallback made and why.
    """

    threshold: int = 5
    consecutive_failures: int = 0
    opened: bool = False
    reason: str = ""

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self, detail: str) -> None:
        self.consecutive_failures += 1
        if not self.opened and self.consecutive_failures >= self.threshold:
            self.opened = True
            self.reason = detail
            METRICS.record_llm_fallback(
                f"model calls stopped after {self.threshold} consecutive failures. "
                f"Last error: {detail} Every remaining decision in this run uses "
                "the deterministic policy, which is why the run finished rather "
                "than hanging. Fix the provider and re-run for model numbers."
            )

    def reset(self) -> None:
        self.consecutive_failures = 0
        self.opened = False
        self.reason = ""


BREAKER = CircuitBreaker()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_models: dict[Role, Any] = {}
_factory_lock = threading.Lock()


def provider_available() -> bool:
    """Is a real model configured for this run?

    Agents ask this before spending a budget slot, so a keyless machine goes
    straight to the deterministic policy instead of failing a call first.
    """
    return SETTINGS.model.provider != "deterministic"


def chat_model(role: Role):
    """A LangChain chat model for the configured provider and tier.

    Cached per role: building a client per call is the kind of thing that looks
    free in a demo and dominates the latency of a 200-persona run.
    """
    if not provider_available():
        raise ModelUnavailable(
            "No model provider is configured. Set GROQ_API_KEY in spark/.env "
            "for the free tier, or SPARK_LLM_PROVIDER=bedrock with AWS "
            "credentials. Runs without a provider use the deterministic policy "
            "and are reported as such."
        )
    with _factory_lock:
        if role in _models:
            return _models[role]
        cfg = SETTINGS.model
        if cfg.provider == "groq":
            if not SETTINGS.groq_key:
                raise ModelUnavailable(
                    "SPARK_LLM_PROVIDER=groq but GROQ_API_KEY is not set. "
                    "Get a free key at console.groq.com and put it in "
                    "spark/.env as GROQ_API_KEY=gsk_..."
                )
            from langchain_groq import ChatGroq

            model = ChatGroq(
                model=cfg.model_id(role),
                temperature=cfg.temperature,
                timeout=cfg.request_timeout_s,
                max_retries=cfg.max_retries,
            )
        elif cfg.provider == "bedrock":
            try:
                from langchain_aws import ChatBedrockConverse
            except ImportError as exc:                  # actionable, not a traceback
                raise ModelUnavailable(
                    "SPARK_LLM_PROVIDER=bedrock but langchain-aws is not "
                    "installed. Run: uv sync --extra aws"
                ) from exc
            model = ChatBedrockConverse(
                model=cfg.model_id(role),
                region_name=cfg.region,
                temperature=cfg.temperature,
            )
        else:                                            # unreachable via config
            raise ModelUnavailable(f"unknown provider {cfg.provider!r}")
        _models[role] = model
        return model


# ---------------------------------------------------------------------------
# The one call
# ---------------------------------------------------------------------------


def structured_call(
    schema: type[T],
    *,
    role: Role,
    agent: str,
    system: str,
    user: str,
    use_budget: bool = True,
) -> T | None:
    """Ask the model for `schema`. Return it, or `None` and a recorded reason.

    `None` is a normal outcome, not an error path — every caller has a
    deterministic policy behind it, and the daily encounter is more important
    than the model's opinion about it.
    """
    if not provider_available():
        return None
    if BREAKER.opened:
        return None
    if use_budget and not BUDGET.take():
        METRICS.record_llm_fallback(
            f"{agent}: run model budget of {BUDGET.limit} calls is spent; this "
            "decision used the deterministic policy"
        )
        return None

    with span(f"model.{agent}", role=role, model=SETTINGS.model.label(role)) as s:
        try:
            model = chat_model(role)
            # include_raw keeps the AIMessage, which carries usage_metadata and
            # any parsing error. Without it we would have the object but no
            # token counts and no way to tell a first-attempt pass from a retry.
            structured = model.with_structured_output(schema, include_raw=True)
            result = structured.invoke(
                [("system", system), ("human", user)]
            )
        except Exception as exc:                        # network, auth, rate limit
            detail = (
                f"{agent}: {SETTINGS.model.label(role)} call failed "
                f"({type(exc).__name__}: {exc}). Falling back to the "
                "deterministic policy for this decision; the encounter is "
                "unaffected."
            )
            METRICS.record_llm_attempt(ok=False, detail=detail)
            METRICS.record_schema(agent, ok=False, detail=detail)
            BREAKER.record_failure(f"{type(exc).__name__}: {exc}")
            s.set_attribute("ok", False)
            return None

        raw = result.get("raw") if isinstance(result, dict) else None
        parsed = result.get("parsed") if isinstance(result, dict) else result
        parsing_error = result.get("parsing_error") if isinstance(result, dict) else None

        _record_usage(role, raw)

        if parsing_error is not None or parsed is None:
            detail = (
                f"{agent}: model returned output that did not validate against "
                f"{schema.__name__} on the first attempt ({parsing_error}). "
                "Falling back to the deterministic policy."
            )
            METRICS.record_schema(agent, ok=False, detail=detail)
            METRICS.record_llm_attempt(ok=False, detail=detail)
            # A schema miss is the model's answer, not the provider being down.
            # It must not trip the breaker, or one badly-shaped output would
            # switch off the model for the rest of the run.
            BREAKER.record_success()
            s.set_attribute("ok", False)
            return None

        METRICS.record_schema(agent, ok=True)
        BREAKER.record_success()
        METRICS.record_llm_attempt(ok=True)
        s.set_attribute("ok", True)
        return parsed


def _record_usage(role: Role, raw: Any) -> None:
    """Pull token counts off whichever shape the provider returned.

    LangChain normalises most of this into `usage_metadata`; the cache fields
    live in a nested dict on the providers that report them. Missing counts are
    recorded as zero rather than skipped, so the call still appears in the
    per-run call count.
    """
    usage = getattr(raw, "usage_metadata", None) or {}
    details = usage.get("input_token_details", {}) if isinstance(usage, dict) else {}
    METRICS.record_tokens(
        role=role,
        provider=SETTINGS.model.provider,
        model=SETTINGS.model.model_id(role),
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        cache_read=int(details.get("cache_read", 0) or 0),
        cache_creation=int(details.get("cache_creation", 0) or 0),
    )
