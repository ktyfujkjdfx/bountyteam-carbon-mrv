import { useId, useState } from 'react';
import { DEMO_ACCOUNTS, ROLE_LABELS } from '../auth';

interface Props {
  onSubmit: (email: string, password: string) => void;
  busy: boolean;
  error: string | null;
  showDemoAccounts: boolean;
  modeNote: string;
}

/**
 * One sentence about the product, one form, and — only in demo mode — the labelled accounts a reviewer
 * can use. Passwords are never pre-filled into a production build and never written to the URL.
 */
export function LoginScreen({ onSubmit, busy, error, showDemoAccounts, modeNote }: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const emailId = useId();
  const passwordId = useId();

  return (
    <main className="lens-login" id="main">
      <section className="lens-login-card" aria-labelledby="lens-login-title">
        <div className="brand">
          <span className="brand-mark">CARBON LENS</span>
          <span className="brand-descriptor">Рабочее место верификатора</span>
        </div>
        <h1 id="lens-login-title">Проверка лесного углеродного заявления по спутниковым данным и общей методике</h1>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!busy) onSubmit(email, password);
          }}
        >
          <label className="lens-field" htmlFor={emailId}>
            <span>Почта</span>
            <input id={emailId} className="input" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} data-testid="lens-login-email" required />
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
          {error && (
            <div className="state state-error compact" role="alert" data-testid="lens-login-error">
              <strong>Вход не выполнен</strong>
              <span>{error}</span>
            </div>
          )}
          <button type="submit" className="btn lens-run" disabled={busy} data-testid="lens-login-submit">
            {busy ? 'Проверяем…' : 'Войти'}
          </button>
        </form>

        {showDemoAccounts && (
          <div className="lens-demo-accounts" data-testid="lens-demo-accounts">
            <h2>Демонстрационные учётные записи</h2>
            <p className="muted small">Существуют только в демонстрационном режиме и не являются доступом к какому-либо сервису.</p>
            <ul>
              {DEMO_ACCOUNTS.map((account) => (
                <li key={account.email}>
                  <button
                    type="button"
                    className="lens-demo-account"
                    onClick={() => {
                      setEmail(account.email);
                      setPassword(account.password);
                      onSubmit(account.email, account.password);
                    }}
                    data-testid={`lens-demo-account-${account.role}`}
                  >
                    <span className="lens-demo-role">{ROLE_LABELS[account.role]}</span>
                    <span className="mono small">{account.email}</span>
                    <span className="muted small">{account.hint}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="muted small" data-testid="lens-login-mode">
          {modeNote}
        </p>
      </section>
    </main>
  );
}
