// ─────────────────────────────────────────────────────────────────────────────
// Formatting Utilities
// Central home for currency / number / date formatting so every view renders
// values identically. Currency is Omani Rial (OMR) — ISO 4217 code "OMR",
// symbol ر.ع. — which conventionally uses THREE decimal places (baisa).
// ─────────────────────────────────────────────────────────────────────────────

export const CURRENCY_CODE = 'OMR';
export const CURRENCY_SYMBOL = 'ر.ع.';

/**
 * Compact currency for KPI cards / tables: "OMR 1.25M", "OMR 12.5K", "OMR 850".
 * Compact form intentionally drops the 3-decimal precision for readability.
 */
export function fmtOMR(value) {
  const v = Number(value) || 0;
  const sign = v < 0 ? '-' : '';
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `${sign}${CURRENCY_CODE} ${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000)     return `${sign}${CURRENCY_CODE} ${(abs / 1_000).toFixed(1)}K`;
  return `${sign}${CURRENCY_CODE} ${abs.toFixed(0)}`;
}

/**
 * Full-precision currency: "OMR 1,250,500.750" — used in detail views / drawers
 * where the exact figure matters. Uses the OMR 3-decimal convention.
 */
export function fmtOMRFull(value) {
  const v = Number(value) || 0;
  return `${CURRENCY_CODE} ${v.toLocaleString(undefined, {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  })}`;
}

/** Plain grouped integer/decimal: "5,834". */
export function fmtNumber(value, decimals = 0) {
  const v = Number(value) || 0;
  return v.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Percentage from a 0–1 ratio or an already-scaled number. */
export function fmtPct(value, { fromRatio = false, decimals = 1 } = {}) {
  const v = (Number(value) || 0) * (fromRatio ? 100 : 1);
  return `${v.toFixed(decimals)}%`;
}

/** Short date: "18 Jul 2026". */
export function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

/** Date + time: "18 Jul 2026, 14:32". */
export function fmtDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

/** Relative "time ago": "3m ago", "2h ago", "5d ago". */
export function fmtTimeAgo(value) {
  if (!value) return '—';
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return '—';
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60)    return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60)    return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)     return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}
