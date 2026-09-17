import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { createClient, resolveConfig } from './api/config';
import './styles.css';

const root = document.getElementById('root');
if (!root) throw new Error('#root not found');

const config = resolveConfig(import.meta.env, window.location.search);

createClient(config).then(
  (client) => {
    createRoot(root).render(
      <StrictMode>
        <App client={client} config={config} />
      </StrictMode>,
    );
  },
  (error: unknown) => {
    root.textContent = `Ошибка конфигурации API: ${error instanceof Error ? error.message : String(error)}`;
  },
);
