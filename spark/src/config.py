"""Every setting in one place, loaded once.

Rule from CLAUDE.md: secrets live in `.env` and are read *here*, never with
`os.environ` scattered through modules. Model choice is configuration, never
hardcoded in an agent — switching provider must be a one-line change.

Nothing in this module does network I/O on import.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RUNS_DIR = ROOT / "runs"          # traces, checkpoints, eval output — gitignored


def _load_dotenv() -> None:
    """Read `spark/.env` into the environment if it exists.

    A real environment variable always wins; this only fills in what is
    missing. Hand-rolled rather than pulling in python-dotenv — it is eight
    lines and one fewer dependency for the organisers to install.
    """
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:                                # actionable error
        raise ValueError(
            f"{name}={raw!r} in .env is not an integer. "
            f"Set it to a whole number, or remove the line to use {default}."
        ) from exc


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name}={raw!r} in .env is not a number. "
            f"Set it to a decimal, or remove the line to use {default}."
        ) from exc


Provider = Literal["deterministic", "groq", "bedrock"]

#: Which tier an agent asks for. See the model-routing table in CLAUDE.md.
Role = Literal["reasoning", "fast"]


@dataclass(frozen=True)
class ModelConfig:
    """Provider routing. One line switches the whole system's provider.

    `deterministic` is not a model. It is an explicit, auditable Python policy
    that stands in for the judgement calls so that the test suite — and a
    six-week simulation over 200 personas — run with no API key and no cost.
    Every metric this project reports is labelled with the provider that
    produced it, so a deterministic run is never presented as a model run.
    """

    provider: Provider = "deterministic"
    groq_reasoning: str = "openai/gpt-oss-20b"
    groq_fast: str = "openai/gpt-oss-20b"
    bedrock_reasoning: str = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
    bedrock_fast: str = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    region: str = "ap-southeast-1"
    temperature: float = 0.0
    request_timeout_s: float = 45.0
    max_retries: int = 2

    def model_id(self, role: Role) -> str:
        if self.provider == "groq":
            return self.groq_reasoning if role == "reasoning" else self.groq_fast
        if self.provider == "bedrock":
            return self.bedrock_reasoning if role == "reasoning" else self.bedrock_fast
        return f"deterministic-policy/{role}"

    def label(self, role: Role) -> str:
        return f"{self.provider}:{self.model_id(role)}"


@dataclass(frozen=True)
class Pricing:
    """USD per million tokens.

    Feeds the organisers' metric 4 (token cost per run) and ours (cost per
    successful connection). Published rates move, so these are read from `.env`
    rather than baked in — the number in the deck is never a stale comment.
    Left at zero when unset, and the report says "unpriced" rather than "free".
    """

    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0

    @property
    def is_set(self) -> bool:
        return self.input_per_mtok > 0 or self.output_per_mtok > 0

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1_000_000 * self.input_per_mtok
            + output_tokens / 1_000_000 * self.output_per_mtok
        )


@dataclass(frozen=True)
class EncounterRules:
    """The product's hard numbers.

    Every one of these is either an invariant or a deliberately-chosen
    parameter. None of them is a magic number sitting in a loop body.
    """

    call_seconds: int = 180                 # INVARIANT 4 — hard stop
    accept_window_minutes: int = 90         # notify -> both accept, else ABANDONED
    consent_window_minutes: int = 1440      # post-call decision window (24h)
    #: Fixed delay between call end and the close-out shown to EITHER party.
    #: Constant by design: if this varied with the other party's answer, the
    #: delay would itself leak that answer (INVARIANT 2).
    close_out_delay_minutes: int = 60
    rematch_cooldown_days: int = 30         # OPEN QUESTION 1 — a guess, see README
    max_lockins: int = 5                    # OPEN QUESTION 2 — attention scarcity
    continuity_note_retention_days: int = 90  # OPEN QUESTION 3
    encounters_per_user_per_day: int = 1
    #: A lock-in with no contact for this long is offered a graceful release.
    lockin_quiet_days: int = 10


@dataclass(frozen=True)
class LoopConfig:
    """Loop discipline is a graded metric. The cap lives here, never inline."""

    max_iterations: int = 5
    target_cap_hit_rate: float = 0.02       # < 2% of runs should reach the cap


@dataclass(frozen=True)
class SimConfig:
    personas: int = 200
    weeks: int = 6
    seed: int = 42
    #: Upper bound on real model calls in one simulation run. When a run needs
    #: more decisions than this, the remainder use the deterministic policy and
    #: the report states exactly how many did. Nothing is dropped silently.
    llm_call_budget: int = 200


@dataclass(frozen=True)
class Settings:
    model: ModelConfig
    pricing_reasoning: Pricing
    pricing_fast: Pricing
    rules: EncounterRules
    loop: LoopConfig
    sim: SimConfig
    trace_console: bool = False
    trace_file: Path = field(default=RUNS_DIR / "trace.jsonl")
    checkpoint_db: Path = field(default=RUNS_DIR / "checkpoints.sqlite")
    #: Raise rather than redact when a user-facing string would leak identity
    #: or location. On in every run we ship; the guardrail tests flip it off to
    #: assert on the verdict object instead of catching an exception.
    strict_guardrails: bool = True

    @property
    def groq_key(self) -> str | None:
        """Read at the point of use, so a key never lands in a dataclass repr,
        a log line or a span attribute."""
        return os.environ.get("GROQ_API_KEY") or None

    def pricing(self, role: Role) -> Pricing:
        return self.pricing_reasoning if role == "reasoning" else self.pricing_fast


def _resolve_provider() -> Provider:
    """Explicit setting wins; otherwise pick what this machine can actually run.

    A missing key is not an error — the deterministic policy is a supported
    path and `README.md` says so. It *is* reported, everywhere the numbers are.
    """
    chosen = os.environ.get("SPARK_LLM_PROVIDER", "").strip().lower()
    if chosen in ("groq", "bedrock", "deterministic"):
        return chosen                                   # type: ignore[return-value]
    if chosen:
        raise ValueError(
            f"SPARK_LLM_PROVIDER={chosen!r} is not recognised. "
            "Use one of: deterministic, groq, bedrock."
        )
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    return "deterministic"


def load_settings() -> Settings:
    """Build the settings object. Called once, for `src.config.SETTINGS`."""
    model = ModelConfig(
        provider=_resolve_provider(),
        groq_reasoning=_env("SPARK_GROQ_REASONING_MODEL", "openai/gpt-oss-20b"),
        groq_fast=_env("SPARK_GROQ_FAST_MODEL", "openai/gpt-oss-20b"),
        bedrock_reasoning=_env(
            "SPARK_BEDROCK_REASONING_MODEL",
            "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
        ),
        bedrock_fast=_env(
            "SPARK_BEDROCK_FAST_MODEL",
            "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        ),
        region=_env("AWS_DEFAULT_REGION", _env("AWS_REGION", "ap-southeast-1")),
        temperature=_env_float("SPARK_TEMPERATURE", 0.0),
    )
    return Settings(
        model=model,
        pricing_reasoning=Pricing(
            _env_float("SPARK_PRICE_REASONING_IN", 0.0),
            _env_float("SPARK_PRICE_REASONING_OUT", 0.0),
        ),
        pricing_fast=Pricing(
            _env_float("SPARK_PRICE_FAST_IN", 0.0),
            _env_float("SPARK_PRICE_FAST_OUT", 0.0),
        ),
        rules=EncounterRules(
            rematch_cooldown_days=_env_int("SPARK_REMATCH_COOLDOWN_DAYS", 30),
            max_lockins=_env_int("SPARK_MAX_LOCKINS", 5),
        ),
        loop=LoopConfig(max_iterations=_env_int("SPARK_MAX_LOOP_ITERATIONS", 5)),
        sim=SimConfig(
            personas=_env_int("SPARK_SIM_PERSONAS", 200),
            weeks=_env_int("SPARK_SIM_WEEKS", 6),
            seed=_env_int("SPARK_SIM_SEED", 42),
            llm_call_budget=_env_int("SPARK_LLM_CALL_BUDGET", 200),
        ),
        trace_console=_env("SPARK_TRACE_CONSOLE", "0") == "1",
    )


#: The single settings instance. Import this; do not call `load_settings()`
#: again — one load keeps every module looking at the same configuration.
SETTINGS = load_settings()
