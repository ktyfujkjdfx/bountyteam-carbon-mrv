// Снимки, на которых видно изменение. Сервис прикладывает к результату оптику на обе даты,
// разностный индекс гари и две маски; до этого блока они существовали только как файлы, и вывод
// «лес потерян» приходилось принимать на слово.
//
// Картинка здесь — доказательство, а не иллюстрация: рядом с каждой стоит сцена, дата, разрешение
// и результат проверки sha256. Снимок, хеш которого не совпал, не показывается вовсе: изображение
// убедительно само по себе, и показать непроверенное опаснее, чем не показать ничего.

import { useEffect } from 'react';
import type { AnalysisResult, Artifact } from '../types';

export interface SnapshotImage {
  role: string;
  artifact: Artifact;
  src: string | null;
  integrity: 'VERIFIED' | 'MISMATCH' | 'UNVERIFIABLE';
}

export type SnapshotsState =
  | { kind: 'hidden' }
  | { kind: 'loading' }
  | { kind: 'ready'; images: SnapshotImage[] }
  | { kind: 'unavailable'; reason: string };

interface Props {
  result: AnalysisResult;
  state: SnapshotsState;
  onLoad: () => void;
}

/** Порядок разговора: что было, что стало, чем это подтверждается. */
export const SNAPSHOT_ROLES: ReadonlyArray<{ role: string; label: string; note: string }> = [
  { role: 'optical_preview_before', label: 'Было', note: 'Оптика Sentinel-2 на начало периода.' },
  { role: 'optical_preview_after', label: 'Стало', note: 'Оптика Sentinel-2 на конец периода, тот же контур и тот же масштаб.' },
  { role: 'dnbr_preview', label: 'Разностный индекс гари', note: 'dNBR между этими двумя датами: светлее — сильнее изменение отражения.' },
  { role: 'zone_mask', label: 'Где выделены зоны', note: 'Маска зон изменений — то, что обведено на карте.' },
  { role: 'paired_valid_mask', label: 'Где сравнение возможно', note: 'Маска пригодных пар наблюдений. Тёмное — сравнивать нечего, это не «изменений не было».' },
];

/** Дата и сцена из строки происхождения вида `RU_TVER_01__S2B_36VVH_20190727_1_L2A`. */
export function sceneOf(provenance: string): { scene: string; date: string | null } {
  const scene = provenance.includes('__') ? provenance.slice(provenance.indexOf('__') + 2) : provenance;
  const match = /(\d{4})(\d{2})(\d{2})/.exec(scene);
  return { scene, date: match ? `${match[3]}.${match[2]}.${match[1]}` : null };
}

function resolutionOf(artifact: Artifact): string | null {
  if (!artifact.resolution) return null;
  const [x] = artifact.resolution;
  const units = artifact.resolution_units === 'metre' ? 'м' : artifact.resolution_units ?? '';
  return `${x} ${units}`.trim();
}

export function Snapshots({ result, state, onLoad }: Props) {
  const available = SNAPSHOT_ROLES.filter((entry) => result.artifacts.some((item) => item.role === entry.role));

  // Снимки грузятся сами: это не дополнительная возможность, а основание вывода, и человек не
  // должен догадываться нажать кнопку, чтобы увидеть, на чём построен ответ. Повторная попытка
  // после отказа — уже по кнопке, чтобы неработающий сервис не опрашивался бесконечно.
  useEffect(() => {
    if (available.length > 0 && state.kind === 'hidden') onLoad();
  }, [available.length, onLoad, state.kind]);

  if (available.length === 0) {
    return (
      <section className="snapshots" aria-label="Снимки участка">
        <p className="muted small" data-testid="lens-snapshots-none">
          К этому результату снимки не приложены: сервис не опубликовал ни оптики, ни масок.
        </p>
      </section>
    );
  }

  return (
    <section className="snapshots" aria-label="Снимки участка" data-testid="lens-snapshots">
      <div className="snapshots-head">
        <h3>На чём видно изменение</h3>
        <p className="muted small">
          Снимки приложены к самому результату и проверяются по sha256 до показа. Ниже — те же даты и тот
          же контур, по которым считался запас.
        </p>
      </div>

      {state.kind === 'loading' && <p className="muted small">Снимки загружаются…</p>}

      {state.kind === 'unavailable' && (
        <div className="state state-warn compact" role="note" data-testid="lens-snapshots-error">
          <strong>Снимки не загрузились</strong>
          <span>{state.reason}</span>
          <button type="button" className="btn btn-small btn-secondary" onClick={onLoad}>
            Попробовать ещё раз
          </button>
        </div>
      )}

      {state.kind === 'ready' && (
        <div className="snapshots-grid">
          {state.images.map((image) => {
            const entry = SNAPSHOT_ROLES.find((item) => item.role === image.role);
            const { scene, date } = sceneOf(image.artifact.provenance);
            const resolution = resolutionOf(image.artifact);
            return (
              <figure key={image.role} className="snapshot" data-testid={`lens-snapshot-${image.role}`}>
                {image.src ? (
                  <img src={image.src} alt={`${entry?.label ?? image.role}: ${scene}`} loading="lazy" />
                ) : (
                  <div className="snapshot-refused" role="note">
                    Хеш файла не совпал с заявленным. Снимок не показан.
                  </div>
                )}
                <figcaption>
                  <b>{entry?.label ?? image.role}</b>
                  {date && <span className="snapshot-date">{date}</span>}
                  <span className="muted small">{entry?.note}</span>
                  <span className="snapshot-meta">
                    <code>{scene}</code>
                    {resolution && <span>{resolution}/пиксель</span>}
                    {image.artifact.crs && <span>{image.artifact.crs}</span>}
                    <span data-integrity={image.integrity}>
                      {image.integrity === 'VERIFIED'
                        ? 'sha256 совпал'
                        : image.integrity === 'MISMATCH'
                          ? 'sha256 не совпал'
                          : 'sha256 не проверен браузером'}
                    </span>
                  </span>
                </figcaption>
              </figure>
            );
          })}
        </div>
      )}
    </section>
  );
}
