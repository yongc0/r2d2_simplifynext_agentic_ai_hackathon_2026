/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `http` switches to HttpAdapter. Anything else (or unset) uses MockAdapter,
   *  so a fresh clone with no backend still runs. */
  readonly VITE_API?: "mock" | "http";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
