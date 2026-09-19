import type { Toast, ToastTone } from '../notify';
import { AlertIcon, CheckIcon, LeafIcon, MinusIcon } from './icons';

const ICON: Record<ToastTone, React.ReactNode> = {
  ok: <CheckIcon size={18} />,
  info: <LeafIcon size={18} />,
  warn: <AlertIcon size={18} />,
  error: <MinusIcon size={18} />,
};

const LABEL: Record<ToastTone, string> = {
  ok: 'Готово',
  info: 'Сообщение',
  warn: 'Внимание',
  error: 'Ошибка',
};

/**
 * Плашки о шагах, справа сверху. Читаются экранным диктором как вежливое сообщение, а не как
 * тревога: работа продолжается, пока их никто не закрыл.
 */
export function Toasts({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: string) => void }) {
  if (toasts.length === 0) return null;
  return (
    <div className="lens-toasts" role="region" aria-label="Уведомления" data-testid="lens-toasts">
      <div aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div key={toast.id} className={`lens-toast tone-${toast.tone}`} data-testid={`lens-toast-${toast.tone}`}>
            <span className="lens-toast-icon" aria-hidden="true">{ICON[toast.tone]}</span>
            <div className="lens-toast-body">
              <strong>{toast.title}</strong>
              {toast.text && <span>{toast.text}</span>}
              {toast.hint && <span className="lens-toast-hint">{toast.hint}</span>}
            </div>
            <button
              type="button"
              className="lens-toast-close"
              onClick={() => onDismiss(toast.id)}
              aria-label={`Закрыть уведомление: ${LABEL[toast.tone]}. ${toast.title}`}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
