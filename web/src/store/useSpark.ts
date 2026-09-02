import { create } from "zustand";

import type {
  AgentEvent,
  ClientState,
  ConsentOutcome,
  ContinuityBrief,
  EncounterCard,
  LockIn,
  Itinerary,
  ProfileChip,
  RevealedPerson,
} from "../api/types";

export interface SavedPlan {
  lockInId: string;
  itinerary: Itinerary;
}

export type IdeaInviteStatus = "none" | "sent" | "accepted" | "declined";

export interface SharedDateIdea {
  ideaId: string;
  lockInId: string;
  title: string;
  detail: string;
  proposedBy: "you" | "them";
  likedByYou: boolean;
  likedByThem: boolean;
  inviteStatus: IdeaInviteStatus;
}

export interface ChatAttachment {
  kind: "photo" | "voice" | "document";
  name: string;
  mimeType: string;
  dataUrl?: string;
}

export interface ChatMessage {
  messageId: string;
  from: "you" | "them";
  text: string;
  sentAt: string;
  attachment?: ChatAttachment;
  moderated?: boolean;
}

/**
 * One store. FRONTEND.md §2: "No state library beyond Zustand", one store,
 * minimal ceremony.
 *
 * The shape follows the encounter's life rather than the screen list, so a
 * route change never invents state and the store can be driven straight from
 * the adapter's scripted run.
 *
 * INVARIANT 3 note: `consentOutcome` distinguishes `declined` from
 * `no_response` so the demo controls can film both branches. Nothing that
 * renders may branch on that difference — the close screen is chosen by
 * `outcome !== "mutual"` and nothing finer. The invariant test asserts it.
 */
interface SparkState {
  // --- who this person said they are (§5.1) --------------------------
  /** The Onboarding Agent's current extraction, rendered. Never a photo, a
   *  height, or an appearance — `ChipKind` has no member for one. */
  chips: ProfileChip[];

  // --- the encounter ------------------------------------------------

  /** True once the evening window has opened. `/home` counts down to it; the
   *  demo strip can open it early, because five minutes of recording does not
   *  contain an evening. */
  windowOpen: boolean;
  clientState: ClientState;
  card: EncounterCard | null;
  /** Set only after a mutual yes. Null at every other point in the flow. */
  revealed: RevealedPerson | null;
  consentOutcome: ConsentOutcome | null;

  // --- the weeks afterwards -----------------------------------------
  lockIns: LockIn[];
  briefs: ContinuityBrief[];
  /** Session-scoped until authenticated persistence/realtime is connected. */
  profilePhoto: string | null;
  savedPlans: SavedPlan[];
  sharedDateIdeas: SharedDateIdea[];
  chats: Record<string, ChatMessage[]>;

  // --- safety ---------------------------------------------------------
  /** Set when someone answers Guardian's check-in with "something felt off".
   *  It has a consequence: the encounter closes without the reveal gate ever
   *  opening, so no name can be exchanged with someone just flagged. */
  guardianConcern: boolean;

  // --- the Director panel (§6) --------------------------------------
  events: AgentEvent[];
  directorOpen: boolean;
  /** Bumped on every reset. The app resubscribes to the agent feed when this
   *  changes — without it, a reset cleared the adapter's timers and the trace
   *  never came back, so the second take filmed an empty panel. */
  traceEpoch: number;

  // --- demo controls (§8) -------------------------------------------
  demoMode: boolean;
  seed: number;

  // --- actions -------------------------------------------------------
  setWindowOpen: (open: boolean) => void;
  setClientState: (state: ClientState) => void;
  setChips: (chips: ProfileChip[]) => void;
  setCard: (card: EncounterCard | null) => void;
  setRevealed: (person: RevealedPerson | null) => void;
  setConsentOutcome: (outcome: ConsentOutcome | null) => void;
  setLockIns: (lockIns: LockIn[]) => void;
  setBriefs: (briefs: ContinuityBrief[]) => void;
  setProfilePhoto: (photo: string | null) => void;
  savePlan: (plan: SavedPlan) => void;
  proposeDateIdea: (idea: Omit<SharedDateIdea, "ideaId" | "likedByYou" | "likedByThem" | "inviteStatus">) => string;
  toggleIdeaLike: (ideaId: string, party: "you" | "them") => void;
  setIdeaInviteStatus: (ideaId: string, status: IdeaInviteStatus) => void;
  sendChatMessage: (lockInId: string, message: Omit<ChatMessage, "messageId" | "sentAt">) => void;
  flagGuardianConcern: () => void;
  pushEvent: (event: AgentEvent) => void;
  toggleDirector: () => void;
  setDemoMode: (on: boolean) => void;
  /** Deterministic reset — §8 requires repeatable takes. */
  reset: (seed?: number) => void;
}

const INITIAL = {
  chips: [] as ProfileChip[],
  windowOpen: false,
  clientState: "IDLE" as ClientState,
  card: null,
  revealed: null,
  consentOutcome: null,
  lockIns: [],
  briefs: [],
  profilePhoto: null,
  savedPlans: [],
  sharedDateIdeas: [],
  chats: {},
  guardianConcern: false,
  events: [],
  directorOpen: false,
  demoMode: false,
  seed: 42,
  traceEpoch: 0,
};

export const useSpark = create<SparkState>((set) => ({
  ...INITIAL,

  setWindowOpen: (windowOpen) => set({ windowOpen }),
  setClientState: (clientState) => set({ clientState }),
  setChips: (chips) => set({ chips }),
  setCard: (card) => set({ card }),
  setRevealed: (revealed) => set({ revealed }),
  setConsentOutcome: (consentOutcome) => set({ consentOutcome }),
  setLockIns: (lockIns) => set({ lockIns }),
  setBriefs: (briefs) => set({ briefs }),
  setProfilePhoto: (profilePhoto) => set({ profilePhoto }),
  savePlan: (plan) =>
    set((state) => ({
      savedPlans: [
        plan,
        ...state.savedPlans.filter(
          (saved) => saved.itinerary.itineraryId !== plan.itinerary.itineraryId,
        ),
      ],
    })),
  proposeDateIdea: (idea) => {
    const ideaId = `idea-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    set((state) => ({
      sharedDateIdeas: state.sharedDateIdeas.some(
        (item) => item.lockInId === idea.lockInId && item.title === idea.title,
      )
        ? state.sharedDateIdeas
        : [
            {
              ...idea,
              ideaId,
              likedByYou: idea.proposedBy === "you",
              likedByThem: idea.proposedBy === "them",
              inviteStatus: "none" as const,
            },
            ...state.sharedDateIdeas,
          ],
    }));
    return ideaId;
  },
  toggleIdeaLike: (ideaId, party) =>
    set((state) => ({
      sharedDateIdeas: state.sharedDateIdeas.map((idea) =>
        idea.ideaId !== ideaId
          ? idea
          : party === "you"
            ? { ...idea, likedByYou: !idea.likedByYou }
            : { ...idea, likedByThem: !idea.likedByThem },
      ),
    })),
  setIdeaInviteStatus: (ideaId, inviteStatus) =>
    set((state) => ({
      sharedDateIdeas: state.sharedDateIdeas.map((idea) =>
        idea.ideaId === ideaId ? { ...idea, inviteStatus } : idea,
      ),
    })),
  sendChatMessage: (lockInId, message) =>
    set((state) => ({
      chats: {
        ...state.chats,
        [lockInId]: [
          ...(state.chats[lockInId] ?? []),
          {
            ...message,
            messageId: `message-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            sentAt: new Date().toISOString(),
          },
        ],
      },
    })),

  flagGuardianConcern: () => set({ guardianConcern: true }),

  pushEvent: (event) =>
    set((s) => ({
      // Bounded. A five-minute recording with an unbounded array is a slow
      // scroll by the end, and nobody watches row 400.
      events: [...s.events, event].slice(-200),
    })),

  toggleDirector: () => set((s) => ({ directorOpen: !s.directorOpen })),
  setDemoMode: (demoMode) => set({ demoMode }),

  reset: (seed = 42) =>
    set((s) => ({
      ...INITIAL,
      // Deliberately preserved across a reset: the operator's panel state and
      // demo flag. Re-opening the Director panel between every take is exactly
      // the friction §8 exists to remove.
      directorOpen: s.directorOpen,
      demoMode: s.demoMode,
      // Bumped, not reset: it is what tells the app to resubscribe to the
      // agent feed for the next take.
      traceEpoch: s.traceEpoch + 1,
      seed,
    })),
}));
