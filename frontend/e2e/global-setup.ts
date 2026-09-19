import type { FullConfig } from '@playwright/test';
import { preview, type PreviewServer } from 'vite';

/**
 * Keep Vite in the Playwright process instead of spawning it through cmd.exe.
 * On Windows the webServer command wrapper could exit while its Node grandchild kept
 * inherited pipes open, leaving a green suite hung forever. The returned teardown is
 * awaited by Playwright and closes every keep-alive connection before the HTTP server.
 */
export default async function globalSetup(_config: FullConfig) {
  if (process.env.E2E_BASE_URL) return undefined;
  const port = Number(process.env.E2E_PORT ?? 4173);
  const server: PreviewServer = await preview({
    configFile: false,
    preview: { host: '127.0.0.1', port, strictPort: true },
  });
  return async () => {
    (server.httpServer as typeof server.httpServer & { closeAllConnections?: () => void }).closeAllConnections?.();
    await new Promise<void>((resolve, reject) => {
      server.httpServer.close((error) => (error ? reject(error) : resolve()));
    });
  };
}
