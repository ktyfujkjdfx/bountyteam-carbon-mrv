import { useId, useState } from 'react';
import { Hash, StatusBadge } from '../../components/common';
import { metaFor } from '../../domain/status';
import { ANCHOR_META, COMPARISON_META } from '../status';
import { passportContent, passportPayload, renderReportHtml, sha256HexOfText, verifyPassportFile, type PassportFileVerdict } from '../passport';
import { PASSPORT_STATUS_TEXT, type PassportStatus } from '../workspace';
import type { AnalysisResult, Proof } from '../types';

type CheckState =
  | { kind: 'idle' }
  | { kind: 'checking' }
  | { kind: 'match'; hash: string }
  | { kind: 'mismatch'; hash: string; expected: string }
  | { kind: 'unsupported' };

type FileState = { kind: 'idle' } | { kind: 'checking' } | PassportFileVerdict;

function download(text: string, name: string, type: string) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

interface Props {
  result: AnalysisResult;
  proof: Proof | null;
  status: PassportStatus;
  submittedBy: string | null;
  finalizedBy: string | null;
  finalizedAt: string | null;
  onIntegrityFailed?: (() => void) | undefined;
}

/** The passport: who produced it, what it hashes, and how a reader repeats the check. */
export function PassportPanel({ result, proof, status, submittedBy, finalizedBy, finalizedAt, onIntegrityFailed }: Props) {
  const [check, setCheck] = useState<CheckState>({ kind: 'idle' });
  const [reportCheck, setReportCheck] = useState<CheckState>({ kind: 'idle' });
  const [fileCheck, setFileCheck] = useState<FileState>({ kind: 'idle' });
  const uploadId = useId();
  const statusText = PASSPORT_STATUS_TEXT[status];

  const verifyContent = async () => {
    setCheck({ kind: 'checking' });
    const hash = await sha256HexOfText(passportContent(result));
    if (hash === null) {
      setCheck({ kind: 'unsupported' });
      return;
    }
    if (hash === result.passport.content_hash) setCheck({ kind: 'match', hash });
    else {
      setCheck({ kind: 'mismatch', hash, expected: result.passport.content_hash });
      onIntegrityFailed?.();
    }
  };

  const verifyReport = async () => {
    setReportCheck({ kind: 'checking' });
    const expected = result.passport.report_hash;
    if (!expected) {
      setReportCheck({ kind: 'unsupported' });
      return;
    }
    const hash = await sha256HexOfText(JSON.stringify({ report: 'carbon-lens-report/2.0.0', content: passportContent(result) }));
    if (hash === null) setReportCheck({ kind: 'unsupported' });
    else setReportCheck(hash === expected ? { kind: 'match', hash } : { kind: 'mismatch', hash, expected });
  };

  const checkFile = async (file: File | null) => {
    if (!file) return;
    setFileCheck({ kind: 'checking' });
    setFileCheck(await verifyPassportFile(await file.text()));
  };

  return (
    <section className="lens-passport" data-testid="lens-passport" aria-label="Паспорт расчёта">
      <header className="batch-header">
        <h3>Паспорт</h3>
        <span className={`badge tone-${statusText.tone}`} data-testid="lens-passport-status" title={statusText.hint}>
          {statusText.label}
        </span>
      </header>

      <dl className="fields">
        <div className="field">
          <dt>Кто подал заявку</dt>
          <dd>{submittedBy ?? 'не указано'}</dd>
        </div>
        <div className="field">
          <dt>Кто финализировал</dt>
          <dd data-testid="lens-passport-finalizer">
            {finalizedBy ? `${finalizedBy} (верификатор)` : 'ещё не финализирован'}
            {finalizedAt && <div className="muted small">{new Date(finalizedAt).toLocaleString('ru-RU')}</div>}
          </dd>
        </div>
        <div className="field">
          <dt>Версии</dt>
          <dd className="mono small">
            схема {result.identity.schema_version} · метод {result.identity.method_version} · данные {result.identity.dataset_version}
          </dd>
        </div>
        <div className="field">
          <dt>Хеш научного содержания</dt>
          <dd>
            <Hash value={result.passport.content_hash} />
          </dd>
        </div>
        <div className="field">
          <dt>Хеш отчёта</dt>
          <dd>
            <Hash value={result.passport.report_hash} />
          </dd>
        </div>
        <div className="field">
          <dt>Сравнение с прошлым расчётом</dt>
          <dd>
            <StatusBadge meta={metaFor(COMPARISON_META, result.passport.comparison_result)} testId="lens-passport-comparison" />
            <div className="muted small">{result.passport.comparison_note}</div>
          </dd>
        </div>
        {proof && (
          <div className="field">
            <dt>Запись в реестр</dt>
            <dd>
              <StatusBadge meta={metaFor(ANCHOR_META, proof.anchor.status)} testId="lens-anchor-status" />
              <div className="muted small">{proof.anchor.note}</div>
            </dd>
          </div>
        )}
      </dl>

      <div className="lens-actions">
        <button
          type="button"
          className="btn btn-small"
          onClick={() => download(passportPayload(result), `carbon-lens-${result.identity.input_hash.slice(2, 14)}.json`, 'application/json')}
          data-testid="lens-passport-download"
        >
          Скачать отчёт (JSON)
        </button>
        <button
          type="button"
          className="btn btn-small btn-secondary"
          onClick={() => download(renderReportHtml(result), `carbon-lens-${result.identity.input_hash.slice(2, 14)}.html`, 'text/html')}
          data-testid="lens-passport-download-html"
        >
          Скачать отчёт (HTML)
        </button>
        <button type="button" className="btn btn-small btn-secondary" onClick={() => void verifyContent()} data-testid="lens-passport-verify">
          Проверить научное содержание
        </button>
        <button type="button" className="btn btn-small btn-secondary" onClick={() => void verifyReport()} data-testid="lens-report-verify">
          Проверить хеш отчёта
        </button>
      </div>

      {[
        { state: check, testId: 'lens-passport-result', label: 'научного содержания' },
        { state: reportCheck, testId: 'lens-report-result', label: 'отчёта' },
      ].map(({ state, testId, label }) => (
        <div key={testId}>
          {state.kind === 'checking' && <div className="state state-loading compact">Пересчёт хеша…</div>}
          {state.kind === 'match' && (
            <div className="state state-ok compact" role="status" data-testid={testId}>
              <strong>Хеш {label} совпадает</strong>
              <span className="muted small">Совпадение означает неизменность содержания, а не истинность расчёта.</span>
            </div>
          )}
          {state.kind === 'mismatch' && (
            <div className="state state-error compact" role="alert" data-testid={testId}>
              <strong>Хеш {label} не совпадает</strong>
              <span className="mono small">получено {state.hash.slice(0, 18)}…</span>
              <span className="mono small">ожидалось {state.expected.slice(0, 18)}…</span>
              <span className="muted small">Это признак изменения содержимого, а не обвинение.</span>
            </div>
          )}
          {state.kind === 'unsupported' && (
            <div className="state state-warn compact" role="status" data-testid={testId}>
              Проверка недоступна: нет Web Crypto или сервис не прислал хеш отчёта.
            </div>
          )}
        </div>
      ))}

      <h4>Проверка полученного файла</h4>
      <p className="muted small">
        Откройте скачанный паспорт: интерфейс пересчитает хеш блока <span className="mono">content</span> и сравнит с блоком{' '}
        <span className="mono">integrity</span>. Изменённая копия обнаруживается этой проверкой.
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
          <span className="muted small">Целостность файла подтверждена. Это не подтверждение методики и не право на единицы.</span>
        </div>
      )}
      {fileCheck.kind === 'mismatch' && (
        <div className="state state-error compact" role="alert" data-testid="lens-passport-file-result">
          <strong>Файл изменён после выдачи</strong>
          <span className="mono small">получено {fileCheck.hash.slice(0, 18)}…</span>
          <span className="mono small">ожидалось {fileCheck.expected.slice(0, 18)}…</span>
        </div>
      )}

      <h4>Источники</h4>
      <ul className="limitations small" data-testid="lens-sources">
        {result.sources.map((source) => (
          <li key={source.source_id}>
            <strong>{source.product}</strong> {source.version}
            <div className="muted">{source.attribution}</div>
            {source.license_url && (
              <div className="mono small">
                <a href={source.license_url} target="_blank" rel="noreferrer noopener">
                  лицензия
                </a>{' '}
                · доступ {source.access_date}
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="muted small">
        Хеш выявляет изменение файла относительно доверенной фиксации. Один хеш не предотвращает повторную продажу и не удостоверяет
        истинность расчёта.
      </p>
    </section>
  );
}
