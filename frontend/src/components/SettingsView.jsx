import { useState, useEffect, useCallback } from 'react';
import {
  Settings as SettingsIcon, Save, RotateCcw, SlidersHorizontal, Info, Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import { api } from '../services/api.js';
import { fmtNumber } from '../utils/format.js';
import { TIER_ORDER, TIER_HEX, TIER_BADGE, tierLabel } from '../utils/risk.js';

// Tier boundary fields, in strict ascending order.
const BOUNDARIES = [
  { key: 'medium',    apiKey: 'medium_risk_threshold',    label: 'Medium',    tier: 'MEDIUM' },
  { key: 'high',      apiKey: 'high_risk_threshold',      label: 'High',      tier: 'HIGH' },
  { key: 'very_high', apiKey: 'very_high_risk_threshold', label: 'Very High', tier: 'VERY_HIGH' },
  { key: 'critical',  apiKey: 'critical_risk_threshold',  label: 'Critical',  tier: 'CRITICAL' },
];

function WeightBar({ label, value, hex }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="font-medium text-gray-600">{label}</span>
        <span className="font-mono font-semibold text-gray-800">{Math.round(value * 100)}%</span>
      </div>
      <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${value * 100}%`, background: hex }} />
      </div>
    </div>
  );
}

export default function SettingsView({ showToast }) {
  const [meta, setMeta]       = useState(null);
  const [bounds, setBounds]   = useState({ medium: 35, high: 55, very_high: 70, critical: 85 });
  const [preview, setPreview] = useState(null);
  const [saving, setSaving]   = useState(false);
  const [dirty, setDirty]     = useState(false);

  const loadMeta = useCallback(async () => {
    try {
      const d = await api.getThresholds();
      setMeta(d);
      setBounds({
        medium: d.thresholds.medium_risk_threshold,
        high: d.thresholds.high_risk_threshold,
        very_high: d.thresholds.very_high_risk_threshold,
        critical: d.thresholds.critical_risk_threshold,
      });
      setDirty(false);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadMeta(); }, [loadMeta]);

  // Live preview of tier migration whenever the boundaries change.
  useEffect(() => {
    const t = setTimeout(() => {
      api.previewThresholds(bounds).then(setPreview).catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [bounds]);

  const ascending = bounds.medium < bounds.high && bounds.high < bounds.very_high && bounds.very_high < bounds.critical;

  const save = async () => {
    if (!ascending) { showToast?.('Thresholds must be strictly increasing.', 'error'); return; }
    setSaving(true);
    try {
      const res = await api.updateThresholds({
        medium_risk_threshold: bounds.medium,
        high_risk_threshold: bounds.high,
        very_high_risk_threshold: bounds.very_high,
        critical_risk_threshold: bounds.critical,
      });
      if (res.status === 'updated') {
        showToast?.('Thresholds updated ✓', 'success');
        setDirty(false);
        loadMeta();
      } else {
        showToast?.(res.reason ?? 'Update rejected', 'error');
      }
    } catch (e) {
      showToast?.(`Save failed: ${e.message}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const setBound = (key, val) => {
    setBounds((prev) => ({ ...prev, [key]: Number(val) }));
    setDirty(true);
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-extrabold tracking-tight text-gray-900 flex items-center gap-2">
          <SettingsIcon className="w-6 h-6 text-slate-500" /> Settings
        </h2>
        <p className="text-sm text-gray-400 mt-0.5">
          Model governance · tune risk tier boundaries and review scoring parameters
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        {/* ── Threshold tuning ─────────────────────────────────────────────── */}
        <div className="xl:col-span-2 bg-white rounded-xl border border-gray-100 shadow-sm p-5 space-y-5">
          <div className="flex items-center justify-between">
            <p className="text-sm font-bold text-gray-700 flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-slate-400" /> Risk Tier Boundaries
            </p>
            <span className="text-xs text-gray-400">Score scale 0–100</span>
          </div>

          {BOUNDARIES.map((b) => (
            <div key={b.key}>
              <div className="flex justify-between text-xs mb-1">
                <span className="flex items-center gap-1.5 font-medium text-gray-600">
                  <span className={clsx('px-2 py-0.5 rounded-full border text-xs font-semibold', TIER_BADGE[b.tier])}>
                    {b.label}
                  </span>
                  threshold
                </span>
                <span className="font-mono font-semibold text-gray-800">{fmtNumber(bounds[b.key], 1)}</span>
              </div>
              <input
                type="range" min={1} max={99} step={1}
                value={bounds[b.key]}
                onChange={(e) => setBound(b.key, e.target.value)}
                className="w-full"
                style={{ accentColor: TIER_HEX[b.tier] }}
              />
            </div>
          ))}

          {!ascending && (
            <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              <Info className="w-4 h-4" /> Boundaries must strictly increase: Medium &lt; High &lt; Very High &lt; Critical.
            </div>
          )}

          <div className="flex gap-2 pt-1 border-t border-gray-100">
            <button
              onClick={loadMeta}
              disabled={!dirty || saving}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40 mt-3"
            >
              <RotateCcw className="w-3.5 h-3.5" /> Revert
            </button>
            <button
              onClick={save}
              disabled={!dirty || saving || !ascending}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg text-white transition-all active:scale-95 disabled:opacity-40 mt-3"
              style={{ background: '#0f172a' }}
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {saving ? 'Saving…' : 'Apply Thresholds'}
            </button>
          </div>
        </div>

        {/* ── Impact preview ───────────────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <p className="text-sm font-bold text-gray-700 mb-1">Impact Preview</p>
          <p className="text-xs text-gray-400 mb-4">
            {preview ? `${fmtNumber(preview.clients_changing_tier)} of ${fmtNumber(preview.clients)} clients would change tier` : 'Computing…'}
          </p>
          <div className="space-y-2">
            {TIER_ORDER.map((t) => {
              const cur = preview?.current_distribution?.[t] ?? 0;
              const prop = preview?.proposed_distribution?.[t] ?? 0;
              const delta = prop - cur;
              return (
                <div key={t} className="flex items-center justify-between text-sm">
                  <span className={clsx('px-2 py-0.5 rounded-full border text-xs font-semibold', TIER_BADGE[t])}>{tierLabel(t)}</span>
                  <span className="flex items-center gap-2 font-mono">
                    <span className="text-gray-400">{cur}</span>
                    <span className="text-gray-300">→</span>
                    <span className="font-semibold text-gray-800">{prop}</span>
                    {delta !== 0 && (
                      <span className={clsx('text-xs font-semibold', delta > 0 ? 'text-red-500' : 'text-emerald-500')}>
                        {delta > 0 ? `+${delta}` : delta}
                      </span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Model metadata ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <p className="text-sm font-bold text-gray-700 mb-4">Component Weights</p>
          <div className="space-y-3">
            <WeightBar label="Credit History" value={meta?.component_weights?.credit_history ?? 0} hex="#4f46e5" />
            <WeightBar label="Behavioural" value={meta?.component_weights?.behavioral ?? 0} hex="#0ea5e9" />
            <WeightBar label="Exposure" value={meta?.component_weights?.exposure ?? 0} hex="#f59e0b" />
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <p className="text-sm font-bold text-gray-700 mb-4">Anomaly Parameters</p>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-gray-500">Velocity window</dt><dd className="font-mono text-gray-800">{meta?.anomaly_parameters?.velocity_window_minutes ?? '—'} min</dd></div>
            <div className="flex justify-between"><dt className="text-gray-500">Max txns / window</dt><dd className="font-mono text-gray-800">{meta?.anomaly_parameters?.velocity_max_transactions ?? '—'}</dd></div>
            <div className="flex justify-between"><dt className="text-gray-500">Structuring floor</dt><dd className="font-mono text-gray-800">{fmtNumber(meta?.anomaly_parameters?.structuring_lower_bound)}</dd></div>
            <div className="flex justify-between"><dt className="text-gray-500">Structuring min count</dt><dd className="font-mono text-gray-800">{meta?.anomaly_parameters?.structuring_min_count ?? '—'}</dd></div>
          </dl>
        </div>

        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
          <p className="text-sm font-bold text-gray-700 mb-4">Model Metadata</p>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-gray-500">Model version</dt><dd className="font-mono text-gray-800">{meta?.model_version ?? '—'}</dd></div>
            <div className="flex justify-between"><dt className="text-gray-500">Environment</dt><dd className="font-mono text-gray-800">{meta?.environment ?? '—'}</dd></div>
            <div className="flex justify-between"><dt className="text-gray-500">Reporting currency</dt><dd className="font-mono text-gray-800">{meta?.reporting_currency ?? 'OMR'}</dd></div>
          </dl>
          <p className="text-xs text-gray-300 mt-4 leading-relaxed">
            Threshold changes apply to the running session only. In production these route through a change-approval workflow.
          </p>
        </div>
      </div>
    </div>
  );
}
