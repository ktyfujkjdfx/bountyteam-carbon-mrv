import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { createClient, resolveConfig } from './api/config';
import { RootErrorBoundary } from './components/RootErrorBoundary';
import { LensApp } from './lens/LensApp';
import './styles.css';

const root = document.getElementById('root');
if (!root) throw new Error('#root not found');

// Served route /lens, plus a hash route so the offline dist also opens from a plain file path.
const isLens = window.location.pathname.replace(/\/+$/, '').endsWith('/lens') || window.location.hash.startsWith('#/lens');

if (isLens) {
  createRoot(root).render(
    <StrictMode>
      <RootErrorBoundary>
        <LensApp />
      </RootErrorBoundary>
    </StrictMode>,
  );
} else {
  const config = resolveConfig(import.meta.env, window.location.search);
  createClient(config).then(
    (client) => {
      createRoot(root).render(
        <StrictMode>
          <RootErrorBoundary>
            <App client={client} config={config} />
          </RootErrorBoundary>
        </StrictMode>,
      );
    },
    (error: unknown) => {
      root.textContent = `Ошибка конфигурации API: ${error instanceof Error ? error.message : String(error)}`;
    },
  );
}
