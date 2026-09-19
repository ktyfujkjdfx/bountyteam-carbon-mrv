// Уведомления о шагах: короткая плашка справа, которая говорит, что произошло и что делать дальше.
//
// Правило одно: уведомление сообщает исход действия, а не заменяет его. Ошибка, которая мешает
// работать, остаётся и на экране рядом с действием — плашка исчезает, а причина никуда не должна
// исчезать вместе с ней.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export type ToastTone = 'ok' | 'info' | 'warn' | 'error';

export interface Toast {
  id: string;
  tone: ToastTone;
  title: string;
  /** Что именно случилось. */
  text?: string;
  /** Что с этим делать и кто может помочь. */
  hint?: string;
}

export type Notify = (toast: Omit<Toast, 'id'>) => void;

/** Сколько плашка держится на экране. Ошибку читают дольше, чем «готово». */
const LIFETIME_MS: Record<ToastTone, number> = { ok: 5000, info: 6000, warn: 9000, error: 12000 };

const MAX_VISIBLE = 4;

export interface Toasts {
  toasts: Toast[];
  notify: Notify;
  dismiss: (id: string) => void;
}

export function useToasts(): Toasts {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const counter = useRef(0);

  const dismiss = useCallback((id: string) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const notify = useCallback<Notify>((toast) => {
    counter.current += 1;
    const id = `toast-${counter.current}`;
    setToasts((current) => [...current, { ...toast, id }].slice(-MAX_VISIBLE));
    const timer = setTimeout(() => {
      timers.current.delete(id);
      setToasts((current) => current.filter((item) => item.id !== id));
    }, LIFETIME_MS[toast.tone]);
    timers.current.set(id, timer);
  }, []);

  // Таймеры не должны переживать экран, который их создал.
  useEffect(() => () => {
    timers.current.forEach((timer) => clearTimeout(timer));
    timers.current.clear();
  }, []);

  return useMemo(() => ({ toasts, notify, dismiss }), [toasts, notify, dismiss]);
}
