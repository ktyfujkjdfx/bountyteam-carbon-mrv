import { useId, useState } from 'react';
import { Empty } from '../../components/common';
import type { FixtureScenarioId } from '../fixtures';
import { FIXTURE_SCENARIOS, FIXTURE_SCENARIO_ORDER } from '../fixtures';
import type { LensArea } from '../types';
import { LENS_MAX_AREA_HA, LENS_YEAR_MAX, LENS_YEAR_MIN } from '../types';

interface Props {
  areas: LensArea[];
  areasLoading: boolean;
  aoiId: string | null;
  onSelectAoi: (aoiId: string) => void;
  geometrySource: string;
  areaHa: number | null;
  yearStart: number;
  yearEnd: number;
  onYears: (start: number, end: number) => void;
  claimedUnits: string;
  onClaimedUnits: (value: string) => void;
  scenario: FixtureScenarioId;
  onScenario: (id: FixtureScenarioId) => void;
  drawing: boolean;
  onToggleDrawing: () => void;
  onImportGeoJson: (text: string) => void;
  onLoadSampleRequest: () => void;
  onRun: () => void;
  busy: boolean;
  validationError: string | null;
}

export function RequestPanel(props: Props) {
  const {
    areas,
    areasLoading,
    aoiId,
    onSelectAoi,
    geometrySource,
    areaHa,
    yearStart,
    yearEnd,
    onYears,
    claimedUnits,
    onClaimedUnits,
    scenario,
    onScenario,
    drawing,
    onToggleDrawing,
    onImportGeoJson,
    onLoadSampleRequest,
    onRun,
    busy,
    validationError,
  } = props;
  const [importText, setImportText] = useState('');
  const [importError, setImportError] = useState<string | null>(null);
  const importId = useId();

  const years: number[] = [];
  for (let y = LENS_YEAR_MIN; y <= LENS_YEAR_MAX; y += 1) years.push(y);

  const handleImport = () => {
    try {
      JSON.parse(importText);
      setImportError(null);
      onImportGeoJson(importText);
    } catch (error) {
      setImportError(`Не удалось разобрать GeoJSON: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  return (
    <div className="lens-request" data-testid="lens-request-panel">
      <h3>Территория</h3>
      {areasLoading && <div className="state state-loading compact">Загрузка участков из data/areas.csv…</div>}
      {!areasLoading && areas.length === 0 && <Empty>Участки не загружены.</Empty>}
      {areas.length > 0 && (
        <label className="lens-field">
          <span>Участок из набора</span>
          <select className="select" value={aoiId ?? ''} onChange={(e) => onSelectAoi(e.target.value)} data-testid="lens-aoi-select">
            {areas.map((area) => (
              <option key={area.aoi_id} value={area.aoi_id}>
                {area.aoi_id} · {area.region}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="lens-actions">
        <button type="button" className={`btn btn-small ${drawing ? '' : 'btn-secondary'}`} onClick={onToggleDrawing} aria-pressed={drawing} data-testid="lens-draw-toggle">
          {drawing ? 'Завершить рисование' : 'Нарисовать контур'}
        </button>
        <button type="button" className="btn btn-small btn-secondary" onClick={onLoadSampleRequest} data-testid="lens-sample-request">
          Подучасток CHECK_TRANSFER_01
        </button>
      </div>

      <details className="evidence-section">
        <summary>Импорт GeoJSON</summary>
        <div className="evidence-section-body">
          <label className="lens-field" htmlFor={importId}>
            <span>Вставьте Feature, FeatureCollection или geometry</span>
          </label>
          <textarea
            id={importId}
            className="input lens-textarea"
            rows={4}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            data-testid="lens-geojson-input"
            spellCheck={false}
          />
          <button type="button" className="btn btn-small btn-secondary" onClick={handleImport} data-testid="lens-geojson-apply">
            Применить контур
          </button>
          {importError && <p className="small warn">{importError}</p>}
        </div>
      </details>

      <dl className="fields">
        <div className="field">
          <dt>Источник контура</dt>
          <dd data-testid="lens-geometry-source">{geometrySource}</dd>
        </div>
        <div className="field">
          <dt>Площадь (с сервера)</dt>
          <dd data-testid="lens-area">
            {areaHa === null ? '—' : `${areaHa.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} га`}
            <div className="muted small">Предел запроса — {LENS_MAX_AREA_HA} га; площадь считает сервис, не интерфейс.</div>
          </dd>
        </div>
      </dl>

      <h3>Период</h3>
      <div className="lens-years">
        <label className="lens-field">
          <span>Начальный год</span>
          <select className="select" value={yearStart} onChange={(e) => onYears(Number(e.target.value), yearEnd)} data-testid="lens-year-start">
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <label className="lens-field">
          <span>Конечный год</span>
          <select className="select" value={yearEnd} onChange={(e) => onYears(yearStart, Number(e.target.value))} data-testid="lens-year-end">
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
      </div>

      <h3>Заявление владельца</h3>
      <label className="lens-field">
        <span>Заявлено единиц (необязательно)</span>
        <input
          className="input"
          inputMode="numeric"
          value={claimedUnits}
          onChange={(e) => onClaimedUnits(e.target.value.trim())}
          data-testid="lens-claim-input"
          aria-describedby="lens-claim-note"
        />
      </label>
      <p className="muted small" id="lens-claim-note">
        Пользовательский ввод, не данные организаторов. Без него все основные функции работают.
      </p>

      <h3>Источник результата</h3>
      <label className="lens-field">
        <span>Помеченный набор F1</span>
        <select className="select" value={scenario} onChange={(e) => onScenario(e.target.value as FixtureScenarioId)} data-testid="lens-scenario-select">
          {FIXTURE_SCENARIO_ORDER.map((id) => (
            <option key={id} value={id}>
              {FIXTURE_SCENARIOS[id].fixture?.label ?? id}
            </option>
          ))}
        </select>
      </label>
      <p className="muted small">
        До подключения Backend экран показывает помеченные значения: условный пример постановки и логические векторы. Это не расчёт по
        выбранному участку.
      </p>

      {validationError && (
        <div className="state state-error compact" role="alert" data-testid="lens-validation-error">
          <strong>Запрос нельзя отправить</strong>
          {validationError}
        </div>
      )}

      <button type="button" className="btn lens-run" onClick={onRun} disabled={busy} data-testid="lens-run">
        {busy ? 'Расчёт выполняется…' : 'Рассчитать'}
      </button>
    </div>
  );
}
