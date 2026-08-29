import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { getAdapter } from "./api/adapter";
import { CloseOut } from "./components/CloseOut";
import { DemoControls, demoModeRequested } from "./components/DemoControls";
import { DeviceFrame } from "./components/DeviceFrame";
import { DirectorPanel, useDirectorHotkey } from "./components/DirectorPanel";
import { useSpark } from "./store/useSpark";
import Call from "./screens/Call";
import Consent from "./screens/Consent";
import Dates from "./screens/Dates";
import Encounter from "./screens/Encounter";
import EncounterWaiting from "./screens/EncounterWaiting";
import Home from "./screens/Home";
import LockIns from "./screens/LockIns";
import Onboarding from "./screens/Onboarding";
import Reveal from "./screens/Reveal";

/**
 * Routes map one-to-one onto the encounter's life, so the client and the
 * backend state machine cannot drift apart quietly (FRONTEND.md §5).
 *
 *   /onboarding         intake
 *   /home               waiting for the window
 *   /encounter          the notification
 *   /encounter/waiting  accepted, waiting for the other side
 *   /call               the three minutes
 *   /call/consent       the decision
 *   /reveal             identity, only after a mutual yes
 *   /lockins            the five slots
 *   /dates              three evenings, once you have both said yes
 */
export default function App() {
  useDirectorHotkey();
  useAgentEvents();
  // Read once at mount. `?demo=1` is an operator's flag, not a user setting.
  const [demo] = useState(demoModeRequested);

  return (
    <>
    <DeviceFrame rail={<DirectorPanel />}>
      <Routes>
        <Route path="/" element={<Navigate to="/home" replace />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/home" element={<Home />} />
        <Route path="/encounter" element={<Encounter />} />
        <Route path="/encounter/waiting" element={<EncounterWaiting />} />
        {/* A decline at the notification, and a no-show after accepting, both
            land on the SAME component the post-call gate uses. One close-out,
            one wording, one timing — INVARIANT 3. */}
        <Route path="/encounter/closed" element={<CloseOut />} />
        <Route path="/call" element={<Call />} />
        <Route path="/call/consent" element={<Consent />} />
        <Route path="/reveal" element={<Reveal />} />
        <Route path="/lockins" element={<LockIns />} />
        {/* Post-reveal only. The screen guards itself on `store.revealed`
            and the backend refuses with 409 — see Dates.tsx. */}
        <Route path="/dates" element={<Dates />} />
        {/* Unknown route lands on home rather than a 404 screen: there is no
            state in this product a stray URL should be able to invent. */}
        <Route path="*" element={<Navigate to="/home" replace />} />
      </Routes>
    </DeviceFrame>
    {/* Outside the frame, so it is never mistaken for part of the product. */}
    {demo ? <DemoControls /> : null}
    </>
  );
}

/**
 * Feed the Director panel.
 *
 * Subscribed once, at the top of the app rather than inside a screen, so the
 * trace survives navigation — an encounter's events span four routes, and a
 * panel that emptied on every transition would show nothing worth watching.
 */
function useAgentEvents() {
  const pushEvent = useSpark((s) => s.pushEvent);
  // Resubscribe after a reset. `MockAdapter.reset()` cancels the timers that
  // drive the scripted trace, so without this the panel went permanently quiet
  // after the first take — the one thing §8 exists to prevent.
  const epoch = useSpark((s) => s.traceEpoch);

  useEffect(() => {
    const stop = getAdapter().subscribeToAgentEvents(pushEvent);
    return stop;
  }, [pushEvent, epoch]);
}
