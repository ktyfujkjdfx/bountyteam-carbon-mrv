const NO_DATA = 'нет данных';

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return NO_DATA;
  return value.toLocaleString('ru-RU', { maximumFractionDigits: digits });
}

export function formatHa(value: number | null | undefined): string {
  return value === null || value === undefined ? NO_DATA : `${formatNumber(value)} га`;
}

export function formatRatio(value: number | null | undefined): string {
  return value === null || value === undefined ? NO_DATA : `${formatNumber(value * 100, 1)} %`;
}

export function formatCount(value: number | null | undefined, unit = 'пикс.'): string {
  return value === null || value === undefined ? NO_DATA : `${value.toLocaleString('ru-RU')} ${unit}`;
}

export function formatUtc(value: string | null | undefined): string {
  if (!value) return NO_DATA;
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}):\d{2}Z$/.exec(value);
  return match ? `${match[1]} ${match[2]} UTC` : value;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return NO_DATA;
  return value.slice(0, 10);
}

export function shortHash(value: string | null | undefined, keep = 10): string {
  if (!value) return '—';
  return value.length <= keep * 2 + 1 ? value : `${value.slice(0, keep)}…${value.slice(-6)}`;
}

// uint256 values arrive as decimal strings; group digits without converting to Number.
export function formatUintString(value: string): string {
  return value.replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f');
}
