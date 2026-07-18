// ─────────────────────────────────────────────────────────────────────────────
// Risk presentation helpers — a single source of truth for tier colours and
// labels so every screen renders the same tier identically.
// ─────────────────────────────────────────────────────────────────────────────

export const TIER_ORDER = ['LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH', 'CRITICAL'];

// Tailwind badge classes per tier (border + bg + text).
export const TIER_BADGE = {
  LOW:       'bg-emerald-50 text-emerald-700 border-emerald-200',
  MEDIUM:    'bg-sky-50 text-sky-700 border-sky-200',
  HIGH:      'bg-amber-50 text-amber-700 border-amber-200',
  VERY_HIGH: 'bg-orange-50 text-orange-700 border-orange-200',
  CRITICAL:  'bg-red-50 text-red-700 border-red-200',
};

// Solid hex per tier for charts / bars.
export const TIER_HEX = {
  LOW:       '#10b981',
  MEDIUM:    '#0ea5e9',
  HIGH:      '#f59e0b',
  VERY_HIGH: '#f97316',
  CRITICAL:  '#ef4444',
};

export const TIER_LABEL = {
  LOW: 'Low',
  MEDIUM: 'Medium',
  HIGH: 'High',
  VERY_HIGH: 'Very High',
  CRITICAL: 'Critical',
};

export function tierLabel(tier) {
  return TIER_LABEL[tier] ?? tier ?? '—';
}

// Colour a composite score (0–100) on the same scale used by the KPI cards.
export function scoreHex(score) {
  const v = Number(score) || 0;
  if (v >= 85) return TIER_HEX.CRITICAL;
  if (v >= 70) return TIER_HEX.VERY_HIGH;
  if (v >= 55) return TIER_HEX.HIGH;
  if (v >= 35) return TIER_HEX.MEDIUM;
  return TIER_HEX.LOW;
}
