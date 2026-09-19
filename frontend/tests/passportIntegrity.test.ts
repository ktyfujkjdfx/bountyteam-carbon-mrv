// The integrity check has to reproduce the service's arithmetic, or it is decoration.
//
// The defect this file exists for: the client hashed a pretty-printed rendering of a content view
// that was missing `risks` and `projection`, while the service hashes the RFC 8785 canonical form of
// the full view. The two never agreed, so every genuine passport was reported as altered — and
// because the offline set computed its hashes the same wrong way, nothing caught it until a real
// service answered.
//
// The golden below is a real result from a live run, kept with the hashes that service computed.
// It is the only thing in this suite that can tell the client's arithmetic from the service's.

import { describe, expect, it } from 'vitest';
import golden from './goldens/live-analysis-result.json';
import {
  REPORT_SCHEMA_VERSION,
  canonicalJson,
  contentHashOf,
  contentView,
  passportPayload,
  reportHashOf,
  verifyPassportFile,
} from '../src/lens/passport';
import { normalizeResult } from '../src/lens/client';
import type { AnalysisResult } from '../src/lens/types';

const live = normalizeResult(golden) as AnalysisResult;

describe('canonical JSON is RFC 8785', () => {
  it('sorts object keys by code unit and emits no whitespace', () => {
    expect(canonicalJson({ b: 1, a: 2, C: 3 })).toBe('{"C":3,"a":2,"b":1}');
  });

  it('sorts nested keys too, because the service hashes the whole tree', () => {
    expect(canonicalJson({ outer: { z: [1, { y: 1, x: 2 }], a: null } })).toBe('{"outer":{"a":null,"z":[1,{"x":2,"y":1}]}}');
  });

  it('keeps array order, which carries meaning', () => {
    expect(canonicalJson([3, 1, 2])).toBe('[3,1,2]');
  });

  it('drops an undefined member exactly as JSON.stringify does', () => {
    expect(canonicalJson({ a: undefined, b: 1 })).toBe('{"b":1}');
  });

  it('refuses a non-finite number rather than writing null in its place', () => {
    expect(() => canonicalJson({ a: Number.NaN })).toThrow();
    expect(() => canonicalJson({ a: Number.POSITIVE_INFINITY })).toThrow();
  });
});

describe('the client reproduces the hashes the service published', () => {
  it('computes the same scientific content hash', async () => {
    expect(await contentHashOf(live)).toBe(golden.passport.content_hash);
  });

  it('computes the same report hash', async () => {
    expect(await reportHashOf(live)).toBe(golden.passport.report_hash);
  });

  it('hashes the report inside the wrapper, not the rendering of it', async () => {
    // The earlier version put a *string* under `content`. Same fields, different preimage.
    const wrong = canonicalJson({ report: REPORT_SCHEMA_VERSION, content: JSON.stringify(contentView(live), null, 2) });
    expect(wrong).not.toBe(canonicalJson({ report: REPORT_SCHEMA_VERSION, content: contentView(live) }));
  });

  it('carries the fields the service hashes, risks and projection included', () => {
    const view = contentView(live);
    expect(Object.keys(view).sort()).toEqual([
      'areas', 'artifacts', 'baseline', 'calculation_status', 'change', 'claim', 'coverage',
      'evidence', 'evidence_status', 'fixture', 'identity', 'limitations', 'notes', 'projection',
      'request', 'risks', 'scenario_values', 'sources', 'timeline', 'uncertainty', 'units', 'zones',
    ]);
  });

  it('leaves out what cannot be part of what was measured', () => {
    const view = contentView(live);
    // A passport cannot hash itself; an analysis id and the shortcut used to name the contour are
    // not properties of the measurement.
    expect(view).not.toHaveProperty('passport');
    expect(view.identity).not.toHaveProperty('analysis_id');
    expect(view.request).not.toHaveProperty('aoi_id');
  });

  it('is unaffected by the defensive normalisation the client applies', async () => {
    // Normalisation fills in shapes the screens rely on. If it ever altered a value inside the
    // content view, the hash would move and every passport would fail — so this is load-bearing.
    expect(await contentHashOf(golden as unknown as AnalysisResult)).toBe(golden.passport.content_hash);
  });
});

describe('a downloaded passport checks out, and a changed one does not', () => {
  it('accepts the file exactly as it was written', async () => {
    expect(await verifyPassportFile(passportPayload(live))).toMatchObject({ kind: 'match' });
  });

  it('accepts the same content reformatted, because formatting is not the result', async () => {
    const parsed = JSON.parse(passportPayload(live)) as Record<string, unknown>;
    expect(await verifyPassportFile(JSON.stringify(parsed))).toMatchObject({ kind: 'match' });
  });

  it('refuses a file whose units were moved', async () => {
    const parsed = JSON.parse(passportPayload(live)) as { content: { units: Record<string, unknown> } };
    parsed.content.units = { ...parsed.content.units, q: 999_999 };
    expect(await verifyPassportFile(JSON.stringify(parsed, null, 2))).toMatchObject({ kind: 'mismatch' });
  });

  it('says it cannot check a file that is not a passport', async () => {
    expect(await verifyPassportFile('{"nope":1}')).toMatchObject({ kind: 'invalid' });
  });
});
