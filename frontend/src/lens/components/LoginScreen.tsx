import { useId, useState } from 'react';
import { ROLE_LABELS, type LensRole } from '../auth';

/** Роль, в которую можно войти одним нажатием. */
export interface RoleEntry {
  username: string;
  role: LensRole;
}

interface Props {
  onSubmit: (username: string, password: string) => void;
  /** Вход одним нажатием: имя учётной записи уходит сервису, пароль подставляет он сам. */
  onRoleEntry?: (username: string) => void;
  roles: RoleEntry[];
  busy: boolean;
  error: string | null;
  modeNote: string;
}

/** Что делает каждая роль — словами, а не названием роли. */
const ROLE_PURPOSE: Record<LensRole, string> = {
  owner: 'подать участок на проверку и следить за ответом сервиса',
  verifier: 'запустить расчёт по спутниковым данным и подтвердить результат',
  investor: 'смотреть подтверждённые результаты, риски и стоимость',
};

const INITIAL: Record<LensRole, string> = { owner: 'В', verifier: 'П', investor: 'И' };

const ROLE_ORDER: LensRole[] = ['owner', 'verifier', 'investor'];

/**
 * Первое, что видит человек: что это за сервис и кнопка на роль. Пароль на экране не нужен —
 * его подставляет сам сервис, и только там, где демонстрационные учётные записи включены. Если
 * их нет, остаётся обычная форма, и тогда она раскрыта сразу.
 */
export function LoginScreen({ onSubmit, onRoleEntry, roles, busy, error, modeNote }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const usernameId = useId();
  const passwordId = useId();
  const ordered = ROLE_ORDER.flatMap((role) => roles.filter((item) => item.role === role));
  const oneClick = ordered.length > 0 && onRoleEntry !== undefined;

  return (
    <main className="lens-login" id="main">
      <section className="lens-login-card" aria-labelledby="lens-login-title">
        <div>
          <div className="brand">
            <span className="brand-mark">CARBON LENS</span>
          </div>
          <h1 id="lens-login-title">Проверка лесных углеродных проектов</h1>
          <p className="lens-login-lead">
            Сервис отвечает на один вопрос: подтверждаются ли заявленные углеродные единицы спутниковыми
            данными и общей методикой. Расчёт выполняет сервис, интерфейс только показывает его результат.
          </p>
        </div>

        {error && (
          <div className="state state-error compact" role="alert" data-testid="lens-login-error">
            <strong>Войти не удалось</strong>
            <span>{error}</span>
          </div>
        )}

        {oneClick && (
          <div className="lens-demo-accounts" data-testid="lens-demo-accounts">
            <strong>Выберите роль</strong>
            <p className="muted small">Нажатие открывает рабочий экран этой роли. Пароль подставляет сервис — в браузер он не попадает.</p>
            <ul>
              {ordered.map((account) => (
                <li key={account.username}>
                  <button
                    type="button"
                    className="lens-demo-account"
                    disabled={busy}
                    onClick={() => onRoleEntry?.(account.username)}
                    data-testid={`lens-demo-account-${account.role}`}
                  >
                    <span className="lens-demo-avatar" aria-hidden="true">{INITIAL[account.role]}</span>
                    <span>
                      <span className="lens-demo-role">{ROLE_LABELS[account.role]}</span>
                      <span className="lens-demo-note">{ROLE_PURPOSE[account.role]}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {busy && <p className="muted small">Входим…</p>}
          </div>
        )}

        <details className="lens-tech" {...(oneClick ? {} : { open: true })}>
          <summary>{oneClick ? 'Войти по имени и паролю' : 'Вход по имени и паролю'}</summary>
          <div className="lens-tech-body">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (!busy) onSubmit(username, password);
              }}
            >
              <label className="lens-field" htmlFor={usernameId}>
                <span>Имя пользователя</span>
                <input id={usernameId} className="input" type="text" autoComplete="username" placeholder="например, owner" value={username} onChange={(event) => setUsername(event.target.value)} data-testid="lens-login-username" required />
                <span className="lens-field-note">Это имя пользователя, а не адрес почты.</span>
              </label>
              <label className="lens-field" htmlFor={passwordId}>
                <span>Пароль</span>
                <input
                  id={passwordId}
                  className="input"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  data-testid="lens-login-password"
                  required
                />
              </label>
              <button type="submit" className="btn lens-run" disabled={busy} data-testid="lens-login-submit">
                {busy ? 'Проверяем…' : 'Войти'}
              </button>
            </form>
          </div>
        </details>

        <p className="muted small" data-testid="lens-login-mode">
          {modeNote}
        </p>
      </section>
    </main>
  );
}
