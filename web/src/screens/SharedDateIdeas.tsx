import { ArrowLeft, Check, Heart, Send, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import { useSpark } from "../store/useSpark";

export default function SharedDateIdeas() {
  const navigate = useNavigate();
  const ideas = useSpark((state) => state.sharedDateIdeas);
  const lockIns = useSpark((state) => state.lockIns);
  const toggleLike = useSpark((state) => state.toggleIdeaLike);
  const setInvite = useSpark((state) => state.setIdeaInviteStatus);

  return (
    <div className={`flex h-full flex-col px-6 ${NAV_HEIGHT_CLASS}`}>
      <header className="mb-5">
        <button
          type="button"
          onClick={() => navigate("/plans")}
          className="mb-3 inline-flex items-center gap-1.5 text-xs font-medium text-navy"
        >
          <ArrowLeft size={15} aria-hidden="true" /> Plans
        </button>
        <h1 className="text-2xl font-semibold tracking-tight text-text">Shared date ideas</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          A common pool for you and your lock-ins. Likes are visible to both people.
        </p>
      </header>

      <div className="no-scrollbar flex flex-1 flex-col gap-3 overflow-y-auto pb-3">
        {ideas.length === 0 ? (
          <div className="rounded-card bg-surface p-5 ring-1 ring-navy/10 ring-inset">
            <p className="text-sm font-medium text-text">No shared ideas yet</p>
            <p className="mt-1.5 text-xs leading-relaxed text-muted">
              Save an idea or turn it into a plan, and it will appear here for both of you.
            </p>
          </div>
        ) : (
          ideas.map((idea) => {
            const person = lockIns.find((item) => item.lockInId === idea.lockInId)?.person;
            const peerName = person?.displayName ?? "Your lock-in";
            const mutual = idea.likedByYou && idea.likedByThem;
            return (
              <article
                key={idea.ideaId}
                className="rounded-card bg-surface p-4 shadow-[0_10px_24px_-20px_rgba(2,0,13,0.55)] ring-1 ring-navy/10 ring-inset"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-semibold tracking-[0.16em] text-navy/65 uppercase">
                      {idea.proposedBy === "you" ? "You proposed" : `${peerName} proposed`}
                    </p>
                    <h2 className="mt-1 text-base font-semibold text-text">{idea.title}</h2>
                    <p className="mt-1 text-xs leading-relaxed text-muted">{idea.detail}</p>
                  </div>
                  {mutual ? (
                    <span className="shrink-0 rounded-pill bg-emerald-100 px-2.5 py-1 text-[10px] font-semibold text-emerald-800">
                      BOTH LIKE
                    </span>
                  ) : null}
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    aria-pressed={idea.likedByYou}
                    onClick={() => toggleLike(idea.ideaId, "you")}
                    className={`inline-flex items-center justify-center gap-2 rounded-pill px-3 py-2.5 text-xs font-semibold ring-1 ring-inset ${idea.likedByYou ? "bg-clay text-white ring-clay" : "bg-cream text-navy ring-navy/15"}`}
                  >
                    <Heart size={14} fill={idea.likedByYou ? "currentColor" : "none"} />
                    You {idea.likedByYou ? "liked" : "like"}
                  </button>
                  <button
                    type="button"
                    aria-pressed={idea.likedByThem}
                    onClick={() => toggleLike(idea.ideaId, "them")}
                    className={`inline-flex items-center justify-center gap-2 rounded-pill px-3 py-2.5 text-xs font-semibold ring-1 ring-inset ${idea.likedByThem ? "bg-peach text-navy ring-clay/25" : "bg-cream text-navy ring-navy/15"}`}
                  >
                    <Heart size={14} fill={idea.likedByThem ? "currentColor" : "none"} />
                    {peerName} {idea.likedByThem ? "liked" : "likes"}
                  </button>
                </div>

                <div className="mt-3 border-t border-navy/10 pt-3">
                  {idea.inviteStatus === "none" ? (
                    <button
                      type="button"
                      onClick={() => setInvite(idea.ideaId, "sent")}
                      className="inline-flex w-full items-center justify-center gap-2 rounded-pill bg-navy px-4 py-3 text-sm font-semibold text-cream"
                    >
                      <Send size={15} /> Send an invite
                    </button>
                  ) : idea.inviteStatus === "sent" ? (
                    <div>
                      <p className="text-center text-xs font-medium text-navy">Invite sent · demo peer response</p>
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        <button type="button" onClick={() => setInvite(idea.ideaId, "accepted")} className="inline-flex items-center justify-center gap-1.5 rounded-pill bg-emerald-600 px-3 py-2.5 text-xs font-semibold text-white">
                          <Check size={14} /> Accept
                        </button>
                        <button type="button" onClick={() => setInvite(idea.ideaId, "declined")} className="inline-flex items-center justify-center gap-1.5 rounded-pill bg-cream px-3 py-2.5 text-xs font-semibold text-clay ring-1 ring-clay/25 ring-inset">
                          <X size={14} /> Decline
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className={`rounded-pill px-4 py-2.5 text-center text-xs font-semibold ${idea.inviteStatus === "accepted" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>
                      Invite {idea.inviteStatus}
                    </p>
                  )}
                </div>
              </article>
            );
          })
        )}
      </div>

      <p className="pt-3 text-center text-[10px] leading-relaxed text-muted">
        Prototype: peer likes and responses are simulated in this shared session.
      </p>
    </div>
  );
}
