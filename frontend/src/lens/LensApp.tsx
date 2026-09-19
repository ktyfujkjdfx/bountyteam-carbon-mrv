import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { MethodologyDialog } from '../components/MethodologyDialog';
import { LensError, type LensApiClient } from './client';
import { createLensClient, resolveLensConfig, switchModeHref, type LensConfig } from './config';
import { FORBIDDEN_NOTE, ROLE_LABELS, demoLogin, fetchMe, login as serviceLogin, logout as serviceLogout, permissionsFor, type LensSession } from './auth';
import { getSession, getToken, setSession, subscribeSession } from './sessionStore';
import { LoginScreen } from './components/LoginScreen';
import { InvestorWorkspace, OwnerWorkspace, VerifierWorkspace } from './components/Workspaces';
import { useWorkspace } from './useWorkspace';

type Route = 'owner' | 'verifier' | 'investor';

function routeFromHash(hash: string): Route | null {
  const value = hash.replace(/^#\/?/, '').split('?')[0];
  return value === 'owner' || value === 'verifier' || value === 'investor' ? value : null;
}

function defaultConfig(): LensConfig {
  const search = typeof window === 'undefined' ? '' : window.location.search;
  const env = (import.meta as unknown as { env?: Record<string, string> }).env ?? {};
  return resolveLensConfig(env, search);
}

export function LensApp({ client: injected, config: injectedConfig }: { client?: LensApiClient; config?: LensConfig }) {
  const [config] = useState<LensConfig>(() => injectedConfig ?? defaultConfig());
  const session = useSyncExternalStore(subscribeSession, getSession, getSession);
  const verifiedRef = useRef(false);
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [route, setRoute] = useState<Route | null>(() => (typeof window === 'undefined' ? null : routeFromHash(window.location.hash)));
  const methodologyRef = useRef<HTMLDialogElement | null>(null);

  const client = useMemo(() => injected ?? createLensClient(config, { getToken }), [injected, config]);

  // A stored service token is confirmed once; a rejected one signs out instead of showing stale data.
  useEffect(() => {
    const stored = getSession();
    if (verifiedRef.current || config.mode === 'fixture' || !stored || stored.source === 'DEMO') {
      verifiedRef.current = true;
      return;
    }
    verifiedRef.current = true;
    let cancelled = false;
    fetchMe({ baseUrl: config.baseUrl }, stored.token)
      .then((confirmed) => {
        if (!cancelled && confirmed) setSession(confirmed);
      })
      .catch(() => {
        if (cancelled) return;
        setSession(null);
        setLoginError('Сессия истекла, войдите снова.');
      });
    return () => {
      cancelled = true;
    };
  }, [config.baseUrl, config.mode]);

  useEffect(() => {
    const onHash = () => setRoute(routeFromHash(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const goTo = useCallback((next: Route) => {
    window.location.hash = `#/${next}`;
    setRoute(next);
  }, []);

  const signIn = useCallback(
    async (username: string, password: string) => {
      if (loginBusy) return;
      setLoginBusy(true);
      setLoginError(null);
      try {
        const next = config.mode === 'fixture' ? demoLogin(username, password) : await serviceLogin({ baseUrl: config.baseUrl }, username, password);
        setSession(next);
        goTo(next.role);
      } catch (error) {
        setLoginError(error instanceof LensError ? error.message : String(error));
      } finally {
        setLoginBusy(false);
      }
    },
    [config.baseUrl, config.mode, goTo, loginBusy],
  );

  const signOut = useCallback(async () => {
    const current = getSession();
    let logoutError: string | null = null;
    if (current?.source === 'SERVICE') {
      try {
        await serviceLogout({ baseUrl: config.baseUrl }, current.token);
      } catch (error) {
        logoutError = error instanceof LensError ? error.message : String(error);
      }
    }
    setSession(null);
    setRoute(null);
    window.location.hash = '';
    setLoginError(logoutError);
  }, [config.baseUrl]);

  if (!session) {
    return (
      <LoginScreen
        onSubmit={(username, password) => void signIn(username, password)}
        busy={loginBusy}
        error={loginError}
        showDemoAccounts={config.demoAccounts}
        modeNote={
          config.mode === 'fixture'
            ? 'Офлайн-режим: значения приходят из помеченного набора, вход выполняется локально.'
            : `Рабочий режим: запросы идут к сервису ${config.baseUrl}.`
        }
      />
    );
  }

  const requested: Route = route ?? session.role;

  return (
    <AuthenticatedShell
      session={session}
      config={config}
      client={client}
      onSignOut={signOut}
      onNavigate={goTo}
      route={requested}
      allowed={requested === session.role}
      methodologyRef={methodologyRef}
    />
  );
}

function AuthenticatedShell({
  session,
  config,
  client,
  onSignOut,
  onNavigate,
  route,
  allowed,
  methodologyRef,
}: {
  session: LensSession;
  config: LensConfig;
  client: LensApiClient;
  onSignOut: () => void;
  onNavigate: (route: Route) => void;
  route: Route;
  allowed: boolean;
  methodologyRef: React.RefObject<HTMLDialogElement | null>;
}) {
  const workspace = useWorkspace(client, session.username);
  const offline = client.kind === 'fixture';
  const permissions = permissionsFor(session.role);
  const actions = [
    permissions.canSubmitRequest ? 'подача заявки' : null,
    permissions.canRunAnalysis ? 'запуск анализа' : null,
    permissions.canFinalize ? 'финализация паспорта' : null,
    permissions.canSeeFinalizedOnly ? 'чтение финализированных паспортов' : null,
  ].filter((item): item is string => item !== null);

  return (
    <div className="app lens">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">CARBON LENS</span>
          <span className="brand-descriptor">{ROLE_LABELS[session.role]}</span>
        </div>
        <nav className="topnav" aria-label="Разделы">
          <button type="button" className="topnav-item" aria-current={route === session.role ? 'page' : undefined} onClick={() => onNavigate(session.role)} data-testid="lens-nav-workspace">
            Рабочее место
          </button>
          <button type="button" className="topnav-item" onClick={() => methodologyRef.current?.showModal()} data-testid="lens-open-methodology">
            Методология
          </button>
          <a className="topnav-item" href="/" data-testid="lens-p0-link">
            MRV P0
          </a>
        </nav>
        <div className="topbar-right">
          <span className={`badge ${offline ? 'tone-review' : 'tone-ok'}`} data-testid="lens-mode">
            {offline ? 'ОФЛАЙН-НАБОР' : 'СЕРВИС'}
          </span>
          <span className="badge tone-neutral" data-testid="lens-role">
            {ROLE_LABELS[session.role]}
          </span>
          <a className="topnav-item small" href={switchModeHref(offline ? 'http' : 'fixture', window.location)} data-testid="lens-mode-switch">
            {offline ? 'к сервису' : 'к офлайн-набору'}
          </a>
          <button type="button" className="topnav-item small" onClick={onSignOut} data-testid="lens-logout">
            Выйти
          </button>
        </div>
      </header>

      <div className={`source-bar ${offline ? 'tone-review-bar' : ''}`} role="note" data-testid="lens-source-bar">
        <span className="dot" aria-hidden="true" />
        <strong data-testid="lens-session-username">{session.username}</strong>
        <span>
          Доступно: {actions.join(', ')}.{' '}
          {offline
            ? 'Офлайн-набор: территории, площади, базовая линия, сцены и события — из официального data/; рассчитанные величины помечены как условный пример или логический вектор.'
            : `Значения рассчитывает сервис ${config.baseUrl}.`}
        </span>
      </div>

      {workspace.catalogError && (
        <div className="state state-error" role="alert" data-testid="lens-catalog-error">
          <strong>Каталог недоступен</strong>
          <span>{workspace.catalogError}</span>
          <span className="muted small">Офлайн-набор не подставляется автоматически: переключение режима — явное действие.</span>
        </div>
      )}

      <main id="main">
        {!allowed ? (
          <div className="state state-warn" role="status" data-testid="lens-forbidden">
            <strong>Экран другой роли</strong>
            <span>{FORBIDDEN_NOTE}</span>
            <span>
              <button type="button" className="btn btn-small btn-secondary" onClick={() => onNavigate(session.role)}>
                Вернуться на своё рабочее место
              </button>
            </span>
          </div>
        ) : (
          <>
            {session.role === 'owner' && <OwnerWorkspace workspace={workspace} session={session} />}
            {session.role === 'verifier' && <VerifierWorkspace workspace={workspace} session={session} offline={offline} />}
            {session.role === 'investor' && <InvestorWorkspace workspace={workspace} session={session} />}
          </>
        )}
      </main>
      <MethodologyDialog ref={methodologyRef} />
    </div>
  );
}
