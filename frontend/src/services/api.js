// ─────────────────────────────────────────────────────────────────────────────
// API Service Layer
// All calls go through Vite's dev-proxy (/api → http://127.0.0.1:8000).
// To call the backend directly (e.g. from a static build), set:
//   const BASE = 'http://127.0.0.1:8000'
// ─────────────────────────────────────────────────────────────────────────────
const BASE = '';

const request = async (path, options = {}) => {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
};

export const api = {
  // ── System ─────────────────────────────────────────────────────────────────
  health: () => request('/health'),

  // ── Reports ────────────────────────────────────────────────────────────────
  getRiskHeatmap: () => request('/api/v1/reports/risk-heatmap'),

  // ── Anomaly Flags ──────────────────────────────────────────────────────────
  getAnomalyFlags: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/v1/anomalies/${qs ? '?' + qs : ''}`);
  },
  getCriticalQueue: () => request('/api/v1/anomalies/critical'),
  resolveFlag: (id, note, status = 'RESOLVED') => {
    const qs = new URLSearchParams({ resolution_status: status, investigator_note: note }).toString();
    return request(`/api/v1/anomalies/${id}/resolve?${qs}`, { method: 'PATCH' });
  },

  // ── AI Adverse Media Alerts ────────────────────────────────────────────────
  getAIAlerts: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/v1/ai-alerts/${qs ? '?' + qs : ''}`);
  },
  acknowledgeAlert: (id, analystName) =>
    request(
      `/api/v1/ai-alerts/${encodeURIComponent(id)}/acknowledge?analyst_name=${encodeURIComponent(analystName)}`,
      { method: 'PATCH' },
    ),

  // ── Pipeline ───────────────────────────────────────────────────────────────
  ingest:         () => request('/api/v1/pipeline/ingest',           { method: 'POST' }),
  scorePortfolio: () => request('/api/v1/pipeline/score-portfolio',  { method: 'POST' }),
  scanAnomalies:  () => request('/api/v1/pipeline/scan-anomalies',   { method: 'POST' }),

  // ── Live Transactions ──────────────────────────────────────────────────────
  getTransactions: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/v1/transactions/${qs ? '?' + qs : ''}`);
  },
  getTransactionStats: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/v1/transactions/stats${qs ? '?' + qs : ''}`);
  },

  // ── Model Stress Tests ─────────────────────────────────────────────────────
  getStressPresets: () => request('/api/v1/stress-tests/presets'),
  runStressTest: (body) =>
    request('/api/v1/stress-tests/run', { method: 'POST', body: JSON.stringify(body) }),

  // ── Settings / Model Governance ────────────────────────────────────────────
  getThresholds: () => request('/api/v1/settings/thresholds'),
  previewThresholds: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/v1/settings/threshold-preview${qs ? '?' + qs : ''}`);
  },
  updateThresholds: (body) =>
    request('/api/v1/settings/thresholds', { method: 'PATCH', body: JSON.stringify(body) }),

  // ── Portfolio Analytics ────────────────────────────────────────────────────
  getPortfolioAnalytics: () => request('/api/v1/analytics/portfolio'),

  // ── Client Explorer ────────────────────────────────────────────────────────
  getClients: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/v1/clients/${qs ? '?' + qs : ''}`);
  },
  getClient360: (id, params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/v1/clients/${encodeURIComponent(id)}/360${qs ? '?' + qs : ''}`);
  },
};
