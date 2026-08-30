import { useState } from "react";

import type { DateMemory } from "../api/types";

/**
 * "What Spark remembers" — and the controls to change it.
 *
 * A memory people cannot see is a profile being built about them. This panel
 * exists so that everything influencing a recommendation can be read, corrected
 * and deleted by the person it is about.
 *
 * It shows the SOURCE of each item, which is the part that usually goes
 * unmentioned: whether Spark was told something or inferred it. Those are
 * different kinds of claim and a person is entitled to treat them differently.
 *
 * Deletion is real. `forgetDateMemory` removes the item from every future
 * ranking — a panel with a delete button that only hides a row would be worse
 * than no panel, because it would look like control.
 */

const DIMENSION_LABEL: Record<string, string> = {
  mood: "Mood",
  budget: "Budget",
  duration: "Length",
  energy: "Energy",
  format: "Kind of thing",
};

const VALUE_OPTIONS: Record<string, string[]> = {
  mood: ["easy", "playful", "adventurous", "meaningful"],
  budget: ["free", "under_20", "under_50", "flexible"],
  duration: ["one_hour", "two_hours", "whole_evening"],
  energy: ["low", "medium", "high"],
  format: ["food", "activity", "outdoors", "learning", "event"],
};

export function DateMemoryPanel({
  memory,
  onCorrect,
  onForget,
}: {
  memory: DateMemory[];
  onCorrect: (memoryId: string, value: string) => void;
  onForget: (memoryId: string) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);

  return (
    <section
      className="rounded-card bg-surface/60 p-4 ring-1 ring-white/[0.06] ring-inset"
      aria-label="What Spark remembers"
    >
      <h2 className="mb-1 text-sm font-medium text-text">
        What Spark remembers
      </h2>
      <p className="mb-3 text-xs leading-relaxed text-muted">
        Only what you asked us to keep, and what we inferred from plans you
        turned down. Change or delete any of it.
      </p>

      {memory.length === 0 ? (
        <p className="text-xs text-muted/70">
          Nothing yet. Tick “Remember this” when you plan, and it will appear
          here.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {memory.map((item) => (
            <li
              key={item.memoryId}
              className="rounded-lg bg-white/[0.03] px-3 py-2.5"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[13px] text-text">
                  {DIMENSION_LABEL[item.dimension] ?? item.dimension}:{" "}
                  <strong className="font-medium">
                    {item.value.replace(/_/g, " ")}
                  </strong>
                </span>
                {/* Told us, or worked it out. Different kinds of claim. */}
                <span
                  className={`shrink-0 rounded-pill px-2 py-0.5 text-[10px] ${
                    item.source === "explicit"
                      ? "bg-accent/15 text-accent-soft"
                      : "bg-white/[0.06] text-muted"
                  }`}
                >
                  {item.source === "explicit" ? "you told us" : "we noticed"}
                </span>
              </div>

              {item.scope === "lockin" ? (
                <p className="mt-1 text-[11px] text-muted/70">
                  Only for this connection.
                </p>
              ) : null}

              {editing === item.memoryId ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(VALUE_OPTIONS[item.dimension] ?? []).map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => {
                        onCorrect(item.memoryId, option);
                        setEditing(null);
                      }}
                      className="rounded-pill bg-white/[0.06] px-3 py-1.5 text-[11px] text-text transition-colors hover:bg-white/[0.12]"
                    >
                      {option.replace(/_/g, " ")}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => setEditing(item.memoryId)}
                    className="text-[11px] text-muted underline-offset-2 hover:text-text hover:underline"
                  >
                    Change
                  </button>
                  <button
                    type="button"
                    onClick={() => onForget(item.memoryId)}
                    className="text-[11px] text-muted underline-offset-2 hover:text-rose-300 hover:underline"
                  >
                    Forget this
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
