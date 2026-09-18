import { useState } from 'react';
import { Hash } from '../../components/common';
import type { LensResult } from '../types';

type VerifyState =
  | { kind: 'idle' }
  | { kind: 'checking' }
  | { kind: 'match'; hash: string }
  | { kind: 'mismatch'; hash: string; expected: string }
  | { kind: 'unsupported' };

// Canonical content that the hash covers. content_sha256 itself is excluded: a value cannot hash itself.
export function passportContent(result: LensResult): string {
  const passport = Object.fromEntries(Object.entries(result.passport).filter(([key]) => key !== 'content_sha256'));
  return JSON.stringify(
    {
      passport,
      request: result.request,
      area_ha: result.area_ha,
      calculation_status: result.calculation_status,
      evidence_status: result.evidence_status,
      stock: result.stock,
      baseline: result.baseline,
      uncertainty: result.uncertainty,
      units: result.units,
      coverage: result.coverage,
      timeline: result.timeline,
      zones: result.zones,
      claim: result.claim,
      sources: result.sources,
      limitations: result.limitations,
      fixture: result.fixture,
    },
    null,
    2,
  );
}

// Downloaded report: canonical content plus the integrity block it is checked against.
export function passportPayload(result: LensResult): string {
  return JSON.stringify({ content: JSON.parse(passportContent(result)), integrity: { content_sha256: result.passport.content_sha256 } }, null, 2);
}

async function sha256Hex(text: string): Promise<string | null> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return null;
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(text));
  return `0x${[...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')}`;
}

export function PassportPanel({ result }: { result: LensResult }) {
  const [verify, setVerify] = useState<VerifyState>({ kind: 'idle' });
  const payload = passportPayload(result);
  const hashed = passportContent(result);

  const download = () => {
    const blob = new Blob([payload], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `carbon-lens-${result.passport.calculation_id}.json`;
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
      </dl>

      <div className="lens-actions">
        <button type="button" className="btn btn-small" onClick={download} data-testid="lens-passport-download">
          Скачать паспорт (JSON)
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

      <h3>Источники и лицензии</h3>
      <ul className="limitations small" data-testid="lens-sources">
        {result.sources.map((source) => (
          <li key={source.source_id}>
            <strong>{source.title}</strong> {source.version} · {source.license}
            <div className="muted">{source.attribution}</div>
          </li>
        ))}
      </ul>

      <h3>Ограничения</h3>
      <ul className="limitations small" data-testid="lens-limitations">
        {result.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
