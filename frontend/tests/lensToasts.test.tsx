/**
 * Уведомления о шагах.
 *
 * Проверяется ровно то, на что полагается интерфейс: сообщение появляется, его можно закрыть, оно
 * само уходит по времени, и свежие сообщения не выбрасывают экран за пределы очереди. Текст
 * сообщений здесь не проверяется — он живёт в местах, где происходит действие.
 */
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Toasts } from '../src/lens/components/Toasts';
import { useToasts, type Notify } from '../src/lens/notify';

function Harness({ onReady }: { onReady: (notify: Notify) => void }) {
  const { toasts, notify, dismiss } = useToasts();
  onReady(notify);
  return <Toasts toasts={toasts} onDismiss={dismiss} />;
}

describe('уведомления о шагах', () => {
  let notify: Notify = () => {};

  beforeEach(() => {
    render(<Harness onReady={(fn) => { notify = fn; }} />);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('пока сообщений нет, на экране ничего не занимает места', () => {
    expect(screen.queryByTestId('lens-toasts')).toBeNull();
  });

  it('показывает исход, причину и подсказку, кто может помочь', () => {
    act(() => notify({
      tone: 'warn',
      title: 'По этому участку показывать нечего',
      text: 'Данных по участку RU_VOLOGDA_02 в этом списке нет.',
      hint: 'Заявку по участку подаёт владелец проекта.',
    }));
    const toast = screen.getByTestId('lens-toast-warn');
    expect(toast).toHaveTextContent('По этому участку показывать нечего');
    expect(toast).toHaveTextContent('RU_VOLOGDA_02');
    expect(toast).toHaveTextContent('владелец проекта');
  });

  it('закрывается по нажатию', async () => {
    const user = userEvent.setup();
    act(() => notify({ tone: 'ok', title: 'Заявка отправлена на проверку' }));
    await user.click(screen.getByRole('button', { name: /Закрыть уведомление/ }));
    expect(screen.queryByTestId('lens-toasts')).toBeNull();
  });

  it('уходит само, и ошибка держится дольше, чем «готово»', () => {
    vi.useFakeTimers();
    act(() => notify({ tone: 'ok', title: 'Готово' }));
    act(() => notify({ tone: 'error', title: 'Расчёт не выполнен' }));
    act(() => vi.advanceTimersByTime(6000));
    expect(screen.queryByTestId('lens-toast-ok')).toBeNull();
    expect(screen.getByTestId('lens-toast-error')).toBeVisible();
    act(() => vi.advanceTimersByTime(7000));
    expect(screen.queryByTestId('lens-toasts')).toBeNull();
  });

  it('держит на экране не больше четырёх сообщений', () => {
    act(() => {
      for (let index = 0; index < 6; index += 1) notify({ tone: 'info', title: `Шаг ${index}` });
    });
    expect(screen.getAllByTestId('lens-toast-info')).toHaveLength(4);
    // Остаются последние: человек читает то, что произошло сейчас.
    expect(screen.getByTestId('lens-toasts')).toHaveTextContent('Шаг 5');
    expect(screen.getByTestId('lens-toasts')).not.toHaveTextContent('Шаг 0');
  });
});
