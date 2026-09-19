// Снимки — единственное место в интерфейсе, где человек видит сам материал, а не число, выведенное
// из него. Поэтому проверяется не «картинка нарисовалась», а то, что рядом с ней стоит сцена, дата
// и результат проверки хеша, и что снимок с несовпавшим хешем не показывается вовсе.

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Snapshots, sceneOf, type SnapshotsState } from '../src/lens/components/Snapshots';
import { createFixtureLensClient } from '../src/lens/fixtureClient';
import type { AnalysisResult, Artifact } from '../src/lens/types';

async function anyResult(): Promise<AnalysisResult> {
  const client = createFixtureLensClient({ queuedMs: 0, runningMs: 0 });
  const accepted = await client.createAnalysis(
    { aoi_id: 'RU_TVER_01', year_start: 2019, year_end: 2024 },
    { idempotencyKey: `k-${Math.random()}` },
  );
  const analysis = await client.getAnalysis(accepted.analysis_id);
  if (!analysis.result) throw new Error('no result');
  return analysis.result;
}

function preview(role: string, provenance: string): Artifact {
  return {
    artifact_id: `${role}.png`,
    role,
    media_type: 'image/png',
    sha256: '0xabc',
    size_bytes: 1024,
    url: `/api/v2/analyses/a/artifacts/${role}.png`,
    bbox_wgs84: [32.9, 56.5, 32.97, 56.63],
    crs: 'EPSG:32636',
    resolution: [20, 20],
    resolution_units: 'metre',
    unit: null,
    provenance,
  };
}

const BEFORE = preview('optical_preview_before', 'RU_TVER_01__S2B_36VVH_20190727_1_L2A');
const AFTER = preview('optical_preview_after', 'RU_TVER_01__S2A_36VVH_20240708_0_L2A');

describe('снимки участка', () => {
  it('читает сцену и дату из строки происхождения', () => {
    expect(sceneOf('RU_TVER_01__S2B_36VVH_20190727_1_L2A')).toEqual({
      scene: 'S2B_36VVH_20190727_1_L2A',
      date: '27.07.2019',
    });
    // Происхождение без даты — не повод молчать про сцену.
    expect(sceneOf('какой-то источник')).toEqual({ scene: 'какой-то источник', date: null });
  });

  it('запрашивает снимки сам, без нажатия кнопки', async () => {
    const result = { ...(await anyResult()), artifacts: [BEFORE, AFTER] };
    const onLoad = vi.fn();
    render(<Snapshots result={result} state={{ kind: 'hidden' }} onLoad={onLoad} />);
    await waitFor(() => expect(onLoad).toHaveBeenCalledTimes(1));
  });

  it('ставит рядом со снимком дату, сцену, разрешение и результат проверки хеша', async () => {
    const result = { ...(await anyResult()), artifacts: [BEFORE, AFTER] };
    const state: SnapshotsState = {
      kind: 'ready',
      images: [
        { role: BEFORE.role, artifact: BEFORE, src: 'blob:before', integrity: 'VERIFIED' },
        { role: AFTER.role, artifact: AFTER, src: 'blob:after', integrity: 'VERIFIED' },
      ],
    };
    render(<Snapshots result={result} state={state} onLoad={vi.fn()} />);
    const before = screen.getByTestId('lens-snapshot-optical_preview_before');
    expect(before).toHaveTextContent('27.07.2019');
    expect(before).toHaveTextContent('S2B_36VVH_20190727_1_L2A');
    expect(before).toHaveTextContent('20 м/пиксель');
    expect(before).toHaveTextContent('sha256 совпал');
    expect(screen.getByTestId('lens-snapshot-optical_preview_after')).toHaveTextContent('08.07.2024');
  });

  it('не показывает снимок, хеш которого не совпал, и говорит об этом', async () => {
    const result = { ...(await anyResult()), artifacts: [BEFORE] };
    const state: SnapshotsState = {
      kind: 'ready',
      images: [{ role: BEFORE.role, artifact: BEFORE, src: null, integrity: 'MISMATCH' }],
    };
    render(<Snapshots result={result} state={state} onLoad={vi.fn()} />);
    const card = screen.getByTestId('lens-snapshot-optical_preview_before');
    expect(card.querySelector('img')).toBeNull();
    expect(card).toHaveTextContent('Хеш файла не совпал');
  });

  it('предлагает повторить, когда снимки не загрузились, и не зацикливает запрос', async () => {
    const result = { ...(await anyResult()), artifacts: [BEFORE] };
    const onLoad = vi.fn();
    const user = userEvent.setup();
    render(<Snapshots result={result} state={{ kind: 'unavailable', reason: 'NETWORK: сервис не ответил' }} onLoad={onLoad} />);
    expect(screen.getByTestId('lens-snapshots-error')).toHaveTextContent('сервис не ответил');
    expect(onLoad).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: /попробовать ещё раз/i }));
    expect(onLoad).toHaveBeenCalledTimes(1);
  });

  it('говорит прямо, когда сервис не приложил ни одного снимка', async () => {
    const result = { ...(await anyResult()), artifacts: [] };
    render(<Snapshots result={result} state={{ kind: 'hidden' }} onLoad={vi.fn()} />);
    expect(screen.getByTestId('lens-snapshots-none')).toHaveTextContent('снимки не приложены');
  });
});
