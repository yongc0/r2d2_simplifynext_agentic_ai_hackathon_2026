import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCheck, HeartHandshake, MessageCircle, Mic2, Search, Sparkles } from "lucide-react";

import { getAdapter } from "../api/adapter";
import { PersonAvatar } from "../components/PersonAvatar";
import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import { useSpark } from "../store/useSpark";
import type { ChatMessage } from "../store/useSpark";

/**
 * /home — spontaneous encounter state. There is intentionally no countdown:
 * when an encounter is ready, the call can begin immediately.
 */

export default function Home() {
  const navigate = useNavigate();
  const lockIns = useSpark((s) => s.lockIns);
  const setLockIns = useSpark((s) => s.setLockIns);
  const forcedOpen = useSpark((s) => s.windowOpen);
  // An empty profile is the one thing that genuinely blocks the product from
  // working, so it is the one thing home will interrupt itself to mention.
  const chips = useSpark((s) => s.chips);
  const chats = useSpark((s) => s.chats);
  const [chatQuery, setChatQuery] = useState("");

  const open = forcedOpen;

  // The lock-in list, if there is one. Failure is silent here on purpose: this
  // screen's job is to be calm, and an error banner about a list that is empty
  // anyway would be the loudest thing on it. `/lockins` reports properly.
  useEffect(() => {
    let cancelled = false;
    getAdapter()
      .getLockIns()
      .then((next) => {
        if (!cancelled) setLockIns(next);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [setLockIns]);

  const active = lockIns.filter((l) => l.state !== "released");
  const filteredChats = active.filter((lockIn) =>
    lockIn.person.displayName.toLowerCase().includes(chatQuery.trim().toLowerCase()),
  );

  return (
    <div className={`no-scrollbar h-full overflow-y-auto px-6 ${NAV_HEIGHT_CLASS}`}>
      <div className="flex flex-col gap-3">
        <p className="text-[10px] font-semibold tracking-[0.2em] text-navy/60 uppercase">
          On Spark
        </p>
        <h1 className="max-w-[19rem] text-[1.75rem] leading-[1.12] font-semibold tracking-tight text-text">
          {open ? "Someone just crossed your path." : "Your next encounter will arrive spontaneously."}
        </h1>

        {open ? (
          <p className="text-sm leading-relaxed text-muted">
            Your anonymous three-minute call is ready now.
          </p>
        ) : (
          <p className="text-sm leading-relaxed text-muted">
            We will let you know the moment a suitable encounter is available.
          </p>
        )}
      </div>

      {open ? (
        <button
          type="button"
          onClick={() => navigate("/encounter")}
          className="mt-8 w-full rounded-pill bg-navy px-6 py-4 text-base font-semibold text-cream shadow-[0_10px_24px_-14px_rgba(7,32,63,0.8)] transition-transform hover:-translate-y-0.5"
        >
          Start the encounter
        </button>
      ) : null}

      {/* Set-up, but only while it is missing. Home is calm because there is
          nothing to scroll — not because it refuses to tell you the product
          cannot match you yet. */}
      {chips.length === 0 ? (
        <button
          type="button"
          onClick={() => navigate("/profile")}
          className="mt-8 w-full rounded-card bg-surface px-4 py-4 text-left shadow-[0_10px_24px_-20px_rgba(2,0,13,0.6)] ring-1 ring-navy/10 ring-inset transition-transform hover:-translate-y-0.5"
        >
          <span className="block text-sm text-text">Set up your profile</span>
          <span className="mt-1 block text-xs leading-relaxed text-muted">
            Spark needs to know what you are here for before it can find anyone.
          </span>
        </button>
      ) : null}

      <section
        aria-labelledby="tonight-works"
        className="mt-8 rounded-card bg-navy p-5 text-cream shadow-[0_14px_32px_-20px_rgba(7,32,63,0.9)]"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[9px] font-semibold tracking-[0.18em] text-cream/75 uppercase">
              One encounter, your pace
            </p>
            <h2 id="tonight-works" className="mt-1 text-lg font-semibold">
              How encounters work
            </h2>
          </div>
          <span className="rounded-pill bg-cream/10 px-2.5 py-1 text-[9px] font-semibold tracking-wide text-cream ring-1 ring-cream/25 ring-inset">
            PRIVATE
          </span>
        </div>

        <ol className="mt-4 grid gap-3">
          <HomeStep
            Icon={Sparkles}
            title="Any moment"
            detail="A suitable encounter can begin spontaneously."
          />
          <HomeStep
            Icon={Mic2}
            title="Three minutes"
            detail="An anonymous voice call with a hard stop."
          />
          <HomeStep
            Icon={HeartHandshake}
            title="You both choose"
            detail="Names unlock only after two private yeses."
          />
        </ol>
      </section>

      <section aria-labelledby="lock-in-chats" className="mt-8 overflow-hidden rounded-card bg-surface shadow-[0_12px_28px_-22px_rgba(2,0,13,0.65)] ring-1 ring-navy/10 ring-inset">
        <div className="flex items-center justify-between px-4 pt-4">
          <div>
            <p className="text-[9px] font-semibold tracking-[0.18em] text-navy/60 uppercase">Lock-in inbox</p>
            <h2 id="lock-in-chats" className="mt-0.5 text-lg font-semibold text-text">Chats</h2>
          </div>
          <button type="button" onClick={() => navigate("/lockins")} aria-label="View all lock-ins" className="grid size-9 place-items-center rounded-full bg-navy text-cream">
            <MessageCircle size={16} />
          </button>
        </div>

        <label className="mx-4 mt-3 flex items-center gap-2 rounded-xl bg-cream/65 px-3 py-2.5 text-navy ring-1 ring-navy/10 ring-inset">
          <Search size={16} aria-hidden="true" />
          <input value={chatQuery} onChange={(event) => setChatQuery(event.target.value)} aria-label="Search lock-in chats" placeholder="Search" className="min-w-0 flex-1 bg-transparent text-sm text-text placeholder:text-muted/65 focus:outline-none" />
        </label>

        <div className="mt-3">
          {filteredChats.length > 0 ? filteredChats.map((lockIn) => {
            const messages = chats[lockIn.lockInId] ?? [];
            const last = messages[messages.length - 1];
            const unread = messages.filter((message) => message.from === "them").length;
            return (
              <button key={lockIn.lockInId} type="button" onClick={() => navigate(`/lockins/${lockIn.lockInId}/chat`)} className="flex w-full items-center gap-3 border-t border-navy/10 px-4 py-3 text-left transition-colors first:border-t-0 hover:bg-cream/45">
                <PersonAvatar photo={lockIn.person.profilePhoto} seed={lockIn.person.avatarSeed} name={lockIn.person.displayName} size={48} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold text-text">{lockIn.person.displayName}</span>
                    <span className="ml-auto flex shrink-0 items-center gap-1 text-[10px] text-muted/70">
                      {last?.from === "you" ? <CheckCheck size={13} className="text-clay" aria-label="Sent" /> : null}
                      {last ? chatTime(last.sentAt) : ""}
                    </span>
                  </span>
                  <span className="mt-0.5 flex items-center gap-2">
                    <span className="truncate text-xs text-muted">{chatPreview(last)}</span>
                    {unread > 0 ? <span className="ml-auto grid size-5 shrink-0 place-items-center rounded-full bg-clay text-[10px] font-semibold text-white">{unread}</span> : null}
                  </span>
                </span>
              </button>
            );
          }) : (
            <p className="border-t border-navy/10 px-4 py-5 text-center text-xs leading-relaxed text-muted">
              {active.length === 0 ? "Your lock-in conversations will appear here." : "No chats match that search."}
            </p>
          )}
        </div>
      </section>

      <p className="mt-8 text-center text-xs font-medium leading-relaxed text-muted">
        One person a day. Three minutes. No names unless you both say yes.
      </p>
    </div>
  );
}

function chatPreview(message: ChatMessage | undefined): string {
  if (!message) return "Start a conversation";
  if (message.text) return message.text;
  if (message.attachment?.kind === "photo") return "Photo";
  if (message.attachment?.kind === "voice") return "Voice message";
  return message.attachment?.name ?? "Document";
}

function chatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(value));
}
function HomeStep({
  Icon,
  title,
  detail,
}: {
  Icon: typeof Sparkles;
  title: string;
  detail: string;
}) {
  return (
    <li className="flex items-center gap-3">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-peach text-navy">
        <Icon size={16} strokeWidth={2} aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-[12px] font-semibold text-cream">{title}</span>
        <span className="block text-[11px] leading-relaxed text-cream/80">{detail}</span>
      </span>
    </li>
  );
}
