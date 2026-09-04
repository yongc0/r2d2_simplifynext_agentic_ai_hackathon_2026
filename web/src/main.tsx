import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { beginFreshProfileSession } from "./api/profile";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

// A profile is intentionally page-session state. Every full page load starts
// at setup, even if the browser refreshed a deeper route such as `/home`.
// Preserve the query string so the presenter's `?demo=1` switch still works.
beginFreshProfileSession();

createRoot(root).render(
  <StrictMode>
    {/* Future flags opt in to v7 behaviour now. Without them React Router
        logs two deprecation warnings on every mount, and a console full of
        warnings is noise while filming and while debugging. */}
    <BrowserRouter
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <App />
    </BrowserRouter>
  </StrictMode>,
);
