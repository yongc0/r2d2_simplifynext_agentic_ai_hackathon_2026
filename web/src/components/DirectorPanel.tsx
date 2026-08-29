import { useEffect, useMemo, useState } from "react";

import type { AgentEvent, AgentName } from "../api/types";
import { useSpark } from "../store/useSpark";

/**
 * The Director panel — FRONTEND.md §6.
 *
 * A live agent trace beside the phone. This is what turns a nice UI into
 * evidence of an agentic system, and §11 says never to cut it: it is worth more
 * to the technical score than Guardian and the real adapter combined.
 *
 * Two of the six graded metrics are on screen, live, at the top: running token
 * cost and elapsed wall time. A judge does not have to take the deck's word for
 * them.
 *
 * Desktop only, hidden by default, toggled with `D` — so the phone can be
 * filmed clean and then the panel revealed.
 */

/** One colour per agent. Muted on purpose: this is a trace, not a dashboard. */
const AGENT_COLOUR: Record<AgentName, string> = {
  onboarding: "text-sky-300",
  match: "text-accent-soft",
  delivery: "text-emerald-300",
  continuity: "text-amber-300",
  communication: "text-violet-300",
  date: "text-teal-300",
  guardian: "text-rose-300",
  safety: "text-slate-300",
};

export function DirectorPanel() {
  const events = useSpark((s) => s.events);
  const open = useSpark((s) => s.directorOpen);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);

  // Wall time since the panel first had something to show. Ticks once a second,
  // which is all a human reads, and keeps this off the animation frame budget
  // that the call screen needs.
  useEffect(() => {
    if (!open || events.length === 0) return;
    const startedAt = Date.now();
    const id = setInterval(
      () => setElapsed(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    );
    return () => clearInterval(id);
  }, [open, events.length === 0]);

  const totals = useMemo(() => {
    let tokens = 0;
    let calls = 0;
    let errors = 0;
    for (const e of events) {
      if (e.tokens) {
        tokens += e.tokens;
        calls += 1;
      }
      if (e.status === "error") errors += 1;
    }
    return { tokens, calls, errors };
  }, [events]);

  if (!open) return null;

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-card bg-surface/70 ring-1 ring-white/[0.06] backdrop-blur">
      <Header
        tokens={totals.tokens}
        calls={totals.calls}
        errors={totals.errors}
        elapsed={elapsed}
        count={events.length}
      />

      <div className="no-scrollbar flex-1 overflow-y-auto px-3 pb-4 font-mono text-[11px] leading-relaxed">
        {events.length === 0 ? (
          <p className="px-2 py-6 text-muted/60">
            Waiting for the first agent to act…
          </p>
        ) : (
          events.map((event, i) => (
            <Row
              key={`${event.ts}-${i}`}
              event={event}
              open={expanded === i}
              onToggle={() => setExpanded(expanded === i ? null : i)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function Header({
  tokens,
  calls,
  errors,
  elapsed,
  count,
}: {
  tokens: number;
  calls: number;
  errors: number;
  elapsed: number;
  count: number;
}) {
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="border-b border-white/[0.06] px-4 py-3">
      <div className="mb-2.5 flex items-baseline justify-between">
        <h2 className="text-[10px] tracking-[0.2em] text-muted uppercase">
          Agent trace
        </h2>
        <span className="font-mono text-[10px] text-muted/60">
          press D to hide
        </span>
      </div>

      {/* Two of the six graded metrics, live. §17: token cost per run, and the
          wall time a run actually took. */}
      <div className="grid grid-cols-3 gap-2 font-mono text-[11px]">
        <Stat label="tokens" value={tokens.toLocaleString()} />
        <Stat label="elapsed" value={`${mm}:${ss}`} />
        <Stat
          label="events"
          value={errors > 0 ? `${count} · ${errors} err` : String(count)}
          alert={errors > 0}
        />
      </div>
      {calls > 0 ? (
        <p className="mt-2 font-mono text-[10px] text-muted/60">
          {calls} model call{calls === 1 ? "" : "s"} · cost shown in
          {" "}
          <span className="text-muted">eval.report</span> when priced
        </p>
      ) : (
        // Never claim a cost we did not measure. A deterministic run has no
        // token spend, and saying "$0.00" would imply it was free rather than
        // that no model was called.
        <p className="mt-2 font-mono text-[10px] text-muted/60">
          no model calls — deterministic policy
        </p>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  alert,
}: {
  label: string;
  value: string;
  alert?: boolean;
}) {
  return (
    <div className="rounded-lg bg-white/[0.03] px-2.5 py-2">
      <div className="text-[9px] tracking-widest text-muted/60 uppercase">
        {label}
      </div>
      <div
        className={`tabular-nums ${alert ? "text-rose-300" : "text-text"}`}
      >
        {value}
      </div>
    </div>
  );
}

function Row({
  event,
  open,
  onToggle,
}: {
  event: AgentEvent;
  open: boolean;
  onToggle: () => void;
}) {
  const time = new Date(event.ts).toLocaleTimeString("en-GB", {
    hour12: false,
  });
  const mark = event.status === "ok" ? "✓" : event.status === "retry" ? "↻" : "✗";

  return (
    <div className="border-b border-white/[0.03] last:border-0">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-baseline gap-2 px-2 py-1.5 text-left transition-colors hover:bg-white/[0.03]"
        aria-expanded={open}
      >
        <span className="shrink-0 text-muted/50 tabular-nums">{time}</span>
        <span className={`w-[92px] shrink-0 ${AGENT_COLOUR[event.agent]}`}>
          {event.agent}
        </span>
        <span className="flex-1 truncate text-text/80">{event.action}</span>
        <span className="shrink-0 text-muted/60 tabular-nums">
          {event.durationMs}ms
        </span>
        {event.tokens ? (
          <span className="w-[60px] shrink-0 text-right text-muted/60 tabular-nums">
            {event.tokens.toLocaleString()}
          </span>
        ) : (
          <span className="w-[60px] shrink-0" />
        )}
        <span
          className={
            event.status === "error" ? "text-rose-300" : "text-emerald-400/70"
          }
        >
          {mark}
        </span>
      </button>

      {/* The rationale the agent returned. §6: a collapsible detail row per
          event — this is where "the agent decided X because Y" is legible. */}
      {open ? (
        <p className="px-2 pb-2.5 pl-[104px] text-[10px] leading-relaxed text-muted">
          {event.detail || "no detail recorded"}
        </p>
      ) : null}
    </div>
  );
}

/**
 * `D` toggles the panel.
 *
 * Ignored while typing, so the onboarding chat does not swallow the letter d
 * into a hidden panel toggle.
 */
export function useDirectorHotkey() {
  const toggle = useSpark((s) => s.toggleDirector);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "d" && e.key !== "D") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (
        el &&
        (el.tagName === "INPUT" ||
          el.tagName === "TEXTAREA" ||
          el.isContentEditable)
      ) {
        return;
      }
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);
}
