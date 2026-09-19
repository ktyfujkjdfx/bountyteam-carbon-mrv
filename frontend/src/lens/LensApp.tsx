import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { MethodologyDialog } from '../components/MethodologyDialog';
import { LensError, type LensApiClient } from './client';
import { createLensClient, resolveLensConfig, switchModeHref, type LensConfig } from './config';
import { DEMO_ACCOUNTS, FORBIDDEN_NOTE, ROLE_LABELS, demoLogin, demoServiceLogin, fetchDemoAccounts, fetchMe, login as serviceLogin, logout as serviceLogout, permissionsFor, type LensSession, type ServiceDemoAccount } from './auth';
import { getSession, getToken, setSession, subscribeSession } from './sessionStore';
import { LoginScreen } from './components/LoginScreen';
import { Toasts } from './components/Toasts';
import { useToasts } from './notify';
import { InvestorWorkspace, OwnerWorkspace, VerifierWorkspace } from './components/Workspaces';
import { useWorkspace } from './useWorkspace';

type Route = 'owner' | 'verifier' | 'investor';

/** Что человек должен сделать на своём экране — одной фразой, без терминов. */
const ROLE_GUIDE: Record<Route, { title: string; text: string }> = {
  owner: {
    title: 'Ваша задача: подать участок на проверку',
    text: 'Выберите участок, укажите период и — если хотите — сколько единиц заявляете. Дальше участок проверит верификатор: расчёт запускает он, а не вы.',
  },
  verifier: {
    title: 'Ваша задача: проверить заявку расчётом',
    text: 'Откройте заявку из очереди и нажмите «Проверить проект». Сервис посчитает по спутниковым данным; после этого результат можно подтвердить — он станет виден инвестору.',
  },
  investor: {
    title: 'Здесь только проверенные результаты',
    text: 'В портфеле видны участки, по которым верификатор подтвердил расчёт. Для каждого показано, сколько единиц подтверждено, чем это ограничено и сколько это стоит по ценам кейса.',
  },
};

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
  // Роли, в которые сервис разрешает войти одним нажатием. В офлайн-режиме это местные
  // помеченные учётные записи, в рабочем — то, что сервис сам объявил.
  const [roles, setRoles] = useState<ServiceDemoAccount[]>(() =>
    config.mode === 'fixture'
      ? DEMO_ACCOUNTS.map((account) => ({ username: account.email, display_name: account.display_name, role: account.role }))
      : []);
  const methodologyRef = useRef<HTMLDialogElement | null>(null);

  // The session is ended where the service says it is over, so an expired one returns the person to
  // the sign-in screen instead of leaving every panel failing with an error they cannot act on.
  const client = useMemo(
    () => injected ?? createLensClient(config, {
      getToken,
      onUnauthorized: () => {
        if (getSession() === null) return;
        setSession(null);
        setLoginError('Сессия истекла, войдите снова.');
      },
    }),
    [injected, config],
  );

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

  // Спрашиваем сервис, какие роли можно открыть нажатием. Пустой ответ — обычное дело: тогда на
  // экране остаётся вход по имени и паролю.
  useEffect(() => {
    if (config.mode === 'fixture') return;
    let cancelled = false;
    fetchDemoAccounts({ baseUrl: config.baseUrl })
      .then((accounts) => {
        if (!cancelled) setRoles(accounts);
      })
      .catch(() => {
        if (!cancelled) setRoles([]);
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

  const enterRole = useCallback(
    async (username: string) => {
      if (loginBusy) return;
      setLoginBusy(true);
      setLoginError(null);
      try {
        const account = DEMO_ACCOUNTS.find((item) => item.email === username);
        const next = config.mode === 'fixture' && account
          ? demoLogin(account.email, account.password)
          : await demoServiceLogin({ baseUrl: config.baseUrl }, username);
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
        onRoleEntry={(username) => void enterRole(username)}
        roles={roles}
        busy={loginBusy}
        error={loginError}
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
  const { toasts, notify, dismiss } = useToasts();
  const workspace = useWorkspace(client, session.username, notify);
  const offline = client.kind === 'fixture';
  const permissions = permissionsFor(session.role);
  const actions = [
    permissions.canSubmitRequest ? 'подача заявки' : null,
    permissions.canRunAnalysis ? 'запуск анализа' : null,
    permissions.canFinalize ? 'подтверждение паспорта' : null,
    permissions.canSeeFinalizedOnly ? 'чтение подтверждённых паспортов' : null,
  ].filter((item): item is string => item !== null);
  const guide = ROLE_GUIDE[session.role];

  return (
    <div className="app lens">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">CARBON LENS</span>
          <span className="brand-descriptor">{ROLE_LABELS[session.role]}</span>
        </div>
        <nav className="topnav" aria-label="Разделы">
          <button type="button" className="topnav-item" aria-current={route === session.role ? 'page' : undefined} onClick={() => onNavigate(session.role)} data-testid="lens-nav-workspace">
            Мой экран
          </button>
          <button type="button" className="topnav-item" onClick={() => methodologyRef.current?.showModal()} data-testid="lens-open-methodology">
            Как считается
          </button>
          <a className="topnav-item" href="/" data-testid="lens-p0-link">
            Дашборд MRV
          </a>
        </nav>
        <div className="topbar-right">
          <span className={`badge ${offline ? 'tone-review' : 'tone-ok'}`} data-testid="lens-mode">
            {offline ? 'Офлайн-набор' : 'Считает сервис'}
          </span>
          <span className="badge tone-neutral" data-testid="lens-role">
            {ROLE_LABELS[session.role]}
          </span>
          <button type="button" className="btn btn-small btn-secondary" onClick={onSignOut} data-testid="lens-logout">
            Выйти
          </button>
        </div>
      </header>

      <div className={`source-bar ${offline ? 'tone-review-bar' : ''}`} role="note" data-testid="lens-source-bar">
        <span className="dot" aria-hidden="true" />
        <strong data-testid="lens-session-username">{session.username}</strong>
        <span>
          {offline
            ? 'Офлайн-набор: числа взяты из помеченного примера, а не рассчитаны по вашему участку.'
            : 'Все числа на экране рассчитал сервис по официальным данным кейса.'}{' '}
          <a className="link-button" href={switchModeHref(offline ? 'http' : 'fixture', window.location)} data-testid="lens-mode-switch">
            {offline ? 'перейти к сервису' : 'открыть офлайн-набор'}
          </a>
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
        {allowed && (
          <div className="lens-guide" data-testid="lens-guide">
            <span className="lens-guide-icon" aria-hidden="true">i</span>
            <span className="lens-guide-text">
              <strong>{guide.title}</strong>
              <span>{guide.text}</span>
            </span>
          </div>
        )}
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
            {session.role === 'owner' && <OwnerWorkspace workspace={workspace} session={session} notify={notify} />}
            {session.role === 'verifier' && <VerifierWorkspace workspace={workspace} session={session} offline={offline} notify={notify} />}
            {session.role === 'investor' && <InvestorWorkspace workspace={workspace} session={session} notify={notify} />}
          </>
        )}
        <details className="lens-tech" data-testid="lens-tech-session">
          <summary>Технические подробности сеанса</summary>
          <div className="lens-tech-body">
            <span>Учётная запись: {session.username} · роль {ROLE_LABELS[session.role]}</span>
            <span>Разрешённые действия: {actions.join(', ')}.</span>
            <span>
              {offline
                ? 'Режим офлайн-набора: помеченные значения, вход выполняется локально.'
                : `Адрес сервиса: ${config.baseUrl}`}
            </span>
            <span className="muted">Запреты проверяет сервис, а не этот экран: запрос без права завершится ответом 403.</span>
          </div>
        </details>
      </main>
      <Toasts toasts={toasts} onDismiss={dismiss} />
      <MethodologyDialog ref={methodologyRef} />
    </div>
  );
}
