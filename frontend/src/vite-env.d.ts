/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_MODE?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEMO_SESSION?: string;
  readonly VITE_DEMO_AUTHORIZATION_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
