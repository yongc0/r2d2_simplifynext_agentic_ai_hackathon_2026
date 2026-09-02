import type { ReactNode } from "react";

/**
 * The phone, on a desktop — FRONTEND.md §3.
 *
 * Under 768px this is a real mobile layout and the frame disappears entirely.
 * At 768px and above the app renders inside a fixed 390x844 device on a warm
 * neutral backdrop.
 *
 * Three details here exist for the camera rather than for the browser:
 *
 *   The frame is a FIXED size, never a percentage. A frame that reflows as the
 *   window changes is layout shift on film, and the screens inside are laid out
 *   against these exact numbers.
 *
 *   The screen area clips (`overflow-hidden`) and scrolls without chrome. A
 *   scrollbar track is the most obvious tell that a phone mockup is a web page.
 *
 *   The right-hand rail is reserved from the start. The Director panel docks
 *   there later (§6); reserving the space now means switching it on does not
 *   move the phone mid-recording.
 */
export function DeviceFrame({
  children,
  rail,
}: {
  children: ReactNode;
  /** Desktop-only side panel. Never part of the phone UI. */
  rail?: ReactNode;
}) {
  return (
    <div className="min-h-dvh w-full bg-backdrop text-text">
      {/* Mobile: full bleed. Desktop: centre the phone, with the rail beside it. */}
      <div
        className="
          min-h-dvh w-full
          md:flex md:items-center md:justify-center md:gap-8 md:p-8
        "
      >
        <Phone>{children}</Phone>

        {rail ? (
          <aside
            className="hidden md:block md:h-[844px] md:w-[420px] md:shrink-0"
            aria-label="Agent activity"
          >
            {rail}
          </aside>
        ) : null}
      </div>
    </div>
  );
}

function Phone({ children }: { children: ReactNode }) {
  return (
    <div
      className="
        relative w-full min-h-dvh bg-bg
        md:min-h-0 md:w-[390px] md:h-[844px] md:shrink-0
        md:rounded-[24px]
        md:shadow-[0_28px_70px_-24px_rgba(2,0,13,0.45),0_10px_28px_-14px_rgba(7,32,63,0.3)]
        md:ring-[6px] md:ring-bezel
      "
    >
      {/*
        The screen. Clipped to the frame's radius so content cannot paint over
        the bezel, and scrolled without visible chrome.
      */}
      <div className="absolute inset-0 overflow-hidden md:rounded-[18px]">
        <div className="no-scrollbar h-full w-full overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  );
}
