import { useId, useState } from 'react';
import { Hash } from '../../components/common';
import { caseSources } from '../data';
import { passportContent, passportPayload, sha256Hex, verifyPassportFile, type PassportFileVerdict } from '../passport';
import type { LensResult } from '../types';

export { passportContent, passportPayload, verifyPassportFile };

type VerifyState =
  | { kind: 'idle' }
  | { kind: 'checking' }
  | { kind: 'match'; hash: string }
  | { kind: 'mismatch'; hash: string; expected: string }
  | { kind: 'unsupported' };

type FileState = { kind: 'idle' } | { kind: 'checking' } | PassportFileVerdict;

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char] ?? char);
}

function fmt(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? '—' : value.toLocaleString('ru-RU', { maximumFractionDigits: digits });
}

/**
 * Readable report with exactly the values on screen. Nothing is recomputed here: every number is taken
 * from the result, and the JSON file remains the machine-checkable original.
 */
export function passportHtml(result: LensResult): string {
  const rows: Array<[string, string]> = [
    ['Контур', result.request.aoi_id ?? result.request.parent_aoi_id ?? 'контур пользователя'],
    ['Период', `${result.request.year_start}–${result.request.year_end}`],
    ['Площадь, га', fmt(result.area_ha, 2)],
    ['Изменение запаса, т C', fmt(result.stock.delta_tc)],
    ['E за период, т CO₂-экв.', fmt(result.stock.e_tco2e)],
    ['E базовой линии, т CO₂-экв.', fmt(result.baseline.e_base_tco2e)],
    ['R, т CO₂-экв.', fmt(result.units.r_tco2e)],
    ['H, т CO₂-экв.', fmt(result.uncertainty.h_tco2e)],
    ['R после вычета за неопределённость', fmt(result.units.r_adj_tco2e)],
    ['Резерв, т CO₂-экв.', fmt(result.units.buffer_tco2e)],
    ['Q, потенциальные единицы', result.units.q === null ? 'Недоступно' : String(result.units.q)],
    ['Причина', result.units.reason_detail ?? result.units.reason ?? '—'],
    ['Статус расчёта', String(result.calculation_status)],
    ['Статус объяснения', String(result.evidence_status)],
    ['Статус заявления', String(result.claim.status)],
    ['Версия схемы', result.passport.schema_version],
    ['Версия методики', result.passport.method_version],
    ['Версия данных', result.passport.dataset_version],
    ['Хеш содержимого', result.passport.content_sha256],
  ];
  const origin = result.fixture
    ? `${result.fixture.kind === 'DOC_EXAMPLE' ? 'Условный пример постановки' : 'Логический вектор'}: ${result.fixture.note}`
    : result.provenance.computed_note;
  return `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Паспорт расчёта ${escapeHtml(result.passport.calculation_id)}</title>
<style>body{font-family:system-ui,sans-serif;max-width:52rem;margin:2rem auto;padding:0 1rem;line-height:1.5}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;vertical-align:top}
.note{background:#fff6e5;border:1px solid #e3c98a;padding:.75rem;border-radius:.4rem}
code{word-break:break-all}</style></head><body>
<h1>Паспорт расчёта Carbon Lens</h1>
<p class="note">${escapeHtml(origin)}</p>
<table><tbody>${rows.map(([key, value]) => `<tr><th>${escapeHtml(key)}</th><td><code>${escapeHtml(value)}</code></td></tr>`).join('')}</tbody></table>
<h2>Источники</h2><ul>${result.sources
    .map((source) => `<li>${escapeHtml(source.title)} ${escapeHtml(source.version)} — ${escapeHtml(source.attribution)}</li>`)
    .join('')}</ul>
<h2>Ограничения</h2><ul>${result.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
<p>Хеш подтверждает неизменность содержимого относительно зафиксированного значения. Он не удостоверяет истинность расчёта и не предотвращает повторную продажу.</p>
</body></html>`;
}

export function PassportPanel({ result }: { result: LensResult }) {
  const [verify, setVerify] = useState<VerifyState>({ kind: 'idle' });
  const [fileCheck, setFileCheck] = useState<FileState>({ kind: 'idle' });
  const uploadId = useId();
  const payload = passportPayload(result);
  const hashed = passportContent(result);
  const sourceRecords = caseSources();

  const download = (text: string, extension: 'json' | 'html', type: string) => {
    const blob = new Blob([text], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `carbon-lens-${result.passport.calculation_id}.${extension}`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const check = async () => {
    setVerify({ kind: 'checking' });
    const hash = await sha256Hex(hashed);
    if (!hash) {
      setVerify({ kind: 'unsupported' });
      return;
    }
    setVerify(hash === result.passport.content_sha256 ? { kind: 'match', hash } : { kind: 'mismatch', hash, expected: result.passport.content_sha256 });
  };

  const checkFile = async (file: File | null) => {
    if (!file) return;
    setFileCheck({ kind: 'checking' });
    setFileCheck(await verifyPassportFile(await file.text()));
  };

  return (
    <div className="lens-passport" data-testid="lens-passport">
      <dl className="fields">
        <div className="field">
          <dt>Идентификатор расчёта</dt>
          <dd className="mono">{result.passport.calculation_id}</dd>
        </div>
        <div className="field">
          <dt>Дата расчёта</dt>
          <dd className="mono">{result.passport.calculated_at}</dd>
        </div>
        <div className="field">
          <dt>Версии</dt>
          <dd className="mono">
            схема {result.passport.schema_version} · метод {result.passport.method_version} · данные {result.passport.dataset_version}
          </dd>
        </div>
        <div className="field">
          <dt>Хеш содержимого</dt>
          <dd>
            <Hash value={result.passport.content_sha256} />
          </dd>
        </div>
        <div className="field">
          <dt>Манифест источников</dt>
          <dd>
            <Hash value={result.passport.source_manifest_sha256} />
          </dd>
        </div>
        <div className="field">
          <dt>Происхождение значений</dt>
          <dd data-testid="lens-passport-origin">
            {result.provenance.computed_by === 'FIXTURE' ? 'Помеченный набор' : 'Расчёт сервиса'}
            <div className="muted small">{result.provenance.computed_note}</div>
          </dd>
        </div>
      </dl>

      <div className="lens-actions">
        <button type="button" className="btn btn-small" onClick={() => download(payload, 'json', 'application/json')} data-testid="lens-passport-download">
          Скачать паспорт (JSON)
        </button>
        <button
          type="button"
          className="btn btn-small btn-secondary"
          onClick={() => download(passportHtml(result), 'html', 'text/html')}
          data-testid="lens-passport-download-html"
        >
          Скачать отчёт (HTML)
        </button>
        <button type="button" className="btn btn-small btn-secondary" onClick={() => void check()} data-testid="lens-passport-verify">
          Проверить целостность
        </button>
      </div>

      {verify.kind === 'checking' && <div className="state state-loading compact">Проверка хеша…</div>}
      {verify.kind === 'match' && (
        <div className="state state-ok compact" role="status" data-testid="lens-passport-result">
          <strong>Содержимое совпадает с зафиксированным хешем</strong>
          <span className="muted small">Хеш подтверждает неизменность файла, но не истинность расчёта.</span>
        </div>
      )}
      {verify.kind === 'mismatch' && (
        <div className="state state-error compact" role="alert" data-testid="lens-passport-result">
          <strong>Содержимое отличается от зафиксированного</strong>
          <span className="mono small">получено {verify.hash.slice(0, 18)}…</span>
          <span className="mono small">ожидалось {verify.expected.slice(0, 18)}…</span>
          <span className="muted small">Это признак изменения файла, а не диагноз «мошенничество».</span>
        </div>
      )}
      {verify.kind === 'unsupported' && (
        <div className="state state-warn compact" role="status" data-testid="lens-passport-result">
          Проверка хеша недоступна в этом браузере (нет Web Crypto).
        </div>
      )}

      <h3>Проверка полученного файла</h3>
      <p className="muted small">
        Откройте скачанный паспорт — интерфейс пересчитает хеш его блока <span className="mono">content</span> и сравнит с блоком{' '}
        <span className="mono">integrity</span>. Изменённая копия отчёта обнаруживается этой проверкой.
      </p>
      <label className="lens-field" htmlFor={uploadId}>
        <span>Файл паспорта (JSON)</span>
      </label>
      <input
        id={uploadId}
        type="file"
        accept="application/json,.json"
        className="input"
        onChange={(event) => void checkFile(event.target.files?.[0] ?? null)}
        data-testid="lens-passport-upload"
      />
      {fileCheck.kind === 'checking' && <div className="state state-loading compact">Проверка файла…</div>}
      {fileCheck.kind === 'invalid' && (
        <div className="state state-warn compact" role="status" data-testid="lens-passport-file-result">
          <strong>Файл не проверен</strong>
          <span>{fileCheck.message}</span>
        </div>
      )}
      {fileCheck.kind === 'match' && (
        <div className="state state-ok compact" role="status" data-testid="lens-passport-file-result">
          <strong>Файл не изменялся</strong>
          <span className="mono small">{fileCheck.calculationId}</span>
          <span className="muted small">Совпадение означает целостность файла, а не подтверждение методики или права на единицы.</span>
        </div>
      )}
      {fileCheck.kind === 'mismatch' && (
        <div className="state state-error compact" role="alert" data-testid="lens-passport-file-result">
          <strong>Файл изменён после выдачи</strong>
          <span className="mono small">{fileCheck.calculationId}</span>
          <span className="mono small">получено {fileCheck.hash.slice(0, 18)}…</span>
          <span className="mono small">ожидалось {fileCheck.expected.slice(0, 18)}…</span>
          <span className="muted small">Проверка показывает расхождение с зафиксированным содержимым, а не намерение автора.</span>
        </div>
      )}

      <h3>Источники и лицензии</h3>
      <ul className="limitations small" data-testid="lens-sources">
        {result.sources.map((source) => {
          const record = sourceRecords.find((entry) => entry.source_id === source.source_id) ?? null;
          return (
            <li key={source.source_id}>
              <strong>{source.title}</strong> {source.version}
              <div className="muted">{source.attribution}</div>
              {record && (
                <div className="muted small">
                  {record.primary_url && (
                    <a href={record.primary_url} target="_blank" rel="noreferrer noopener">
                      продукт
                    </a>
                  )}
                  {record.license_url && (
                    <>
                      {' · '}
                      <a href={record.license_url} target="_blank" rel="noreferrer noopener">
                        лицензия
                      </a>
                    </>
                  )}
                  {record.doi && <> · DOI {record.doi}</>}
                  {record.accessed && <> · доступ {record.accessed}</>}
                </div>
              )}
              {record?.limitations && <div className="muted small">{record.limitations}</div>}
            </li>
          );
        })}
      </ul>

      <h3>Ограничения</h3>
      <ul className="limitations small" data-testid="lens-limitations">
        {result.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p className="muted small">
        Один хеш не предотвращает повторную продажу и не удостоверяет истинность расчёта: учёт уникального выпуска и передачи единиц — это
        отдельная система.
      </p>
    </div>
  );
}
