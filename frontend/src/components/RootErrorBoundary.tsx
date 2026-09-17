import { Component, Fragment, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  onReload?: () => void;
}

interface State {
  error: Error | null;
  attempt: number;
}

const MAX_MESSAGE = 160;

function shortMessage(error: Error): string {
  const firstLine = (error.message || error.name || 'Неизвестная ошибка').split('\n')[0] ?? '';
  return firstLine.length > MAX_MESSAGE ? `${firstLine.slice(0, MAX_MESSAGE)}…` : firstLine;
}

// Last line of defence: an unexpected render error must never leave #root empty.
export class RootErrorBoundary extends Component<Props, State> {
  override state: State = { error: null, attempt: 0 };

  static getDerivedStateFromError(error: unknown): Partial<State> {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Dashboard render error', error, info.componentStack);
  }

  private readonly recover = () => {
    this.setState((s) => ({ error: null, attempt: s.attempt + 1 }));
  };

  private readonly reload = () => {
    if (this.props.onReload) this.props.onReload();
    else window.location.reload();
  };

  override render(): ReactNode {
    const { error, attempt } = this.state;
    if (!error) return <Fragment key={attempt}>{this.props.children}</Fragment>;
    return (
      <div className="app">
        <main id="main">
          <section className="state state-error fatal" role="alert" data-testid="root-error-boundary">
            <strong>Интерфейс не смог отобразить данные</strong>
            <span>
              Произошла непредвиденная ошибка отображения. Данные Backend и операции не изменены; перезагрузите интерфейс или попробуйте
              восстановить текущий экран.
            </span>
            <span className="muted mono" data-testid="root-error-message">
              {shortMessage(error)}
            </span>
            <span className="badge-row">
              <button type="button" className="btn btn-small" onClick={this.reload} data-testid="root-error-reload">
                Перезагрузить страницу
              </button>
              <button type="button" className="btn btn-small btn-secondary" onClick={this.recover} data-testid="root-error-recover">
                Восстановить интерфейс
              </button>
            </span>
          </section>
        </main>
      </div>
    );
  }
}
