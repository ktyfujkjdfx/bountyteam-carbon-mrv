import type { Ref } from 'react';

const STEPS: ReadonlyArray<[string, string]> = [
  ['Наблюдение', 'Пара сцен Sentinel-2 L2A (до / после) по утверждённой геометрии участка; каналы B04, B08, B8A, B12 и SCL. Scene ID, дата съёмки и provider входят в evidence.'],
  ['Контроль качества', 'Scene Classification Layer исключает no-data, дефектные пиксели, тени, воду, облака, cirrus и снег. Считаются только парно-валидные пиксели на единой 20-метровой сетке.'],
  ['Лесной сигнал', 'NDVI (B08, B04) до и после; NBR (B8A, B12) и dNBR. Порог изменения dNBR ≥ 0.27, связные компоненты ≥ 1 га, площадь — по числу пикселей.'],
  ['Независимый сигнал', 'Точки NASA FIRMS (VIIRS) в окне наблюдения и в пределах 500 м от маски изменения. Это тепловые аномалии, не периметр пожара.'],
  ['Evidence quality', 'Backend пересчитывает качество: paired-valid forest ratio ≥ 0.85 → SUFFICIENT, 0.70–0.85 или несопоставимые сезоны → REVIEW_REQUIRED, ниже → INSUFFICIENT. EQS = доля покрытия × 100, не вероятность.'],
  ['Решение policy v1', 'NO_CHANGE + SUFFICIENT → NO_RESTRICTION. Изменение ≥ 5 га и ≥ 1 % baseline forest с поддержкой FIRMS → FREEZE_REQUESTED / FIRE_REVERSAL. Иначе → REVIEW_REQUIRED. Пороги — demo policy, не стандарт рынка.'],
  ['Доказуемость', 'Backend хранит канонические JCS-байты evidence и считает SHA-256 evidence_hash и decision_hash; /proof сверяет пересчитанный хеш.'],
  ['Реестр', 'issue / buy / transfer / freeze исполняет контракт. CONFIRMED — только после receipt status 1, ожидаемого события и readback. FROZEN — временное ограничение прототипа, не юридическое аннулирование.'],
];

export function MethodologyDialog({ ref }: { ref: Ref<HTMLDialogElement> }) {
  return (
    <dialog ref={ref} className="methodology" aria-labelledby="methodology-title" data-testid="methodology">
      <div className="methodology-header">
        <div>
          <div className="label">BountyTeam · contracts-v1.0.0</div>
          <h2 id="methodology-title">Методология MRV-доказательства</h2>
        </div>
        <form method="dialog">
          <button type="submit" className="btn btn-small btn-secondary">
            Закрыть
          </button>
        </form>
      </div>
      <div className="methodology-body">
        <p className="small muted">
          Прототип показывает, как воспроизводимое спутниковое наблюдение может запускать временное ограничение обращения тестовой серии по
          прозрачной политике оператора. Он не заменяет сертификацию, расчёт углерода и независимую проверку.
        </p>
        <ol className="method-steps">
          {STEPS.map(([title, text]) => (
            <li key={title}>
              <b>{title}</b>
              <span>{text}</span>
            </li>
          ))}
        </ol>
        <h3>Вне контракта v1</h3>
        <p className="small muted">
          Сравнение с контрольной территорией, leakage buffer, оценки запаса углерода (tCO₂e) и временные ряды NDVI не передаются Backend API
          v1, поэтому интерфейс их не показывает и не вычисляет.
        </p>
      </div>
    </dialog>
  );
}
