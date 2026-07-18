import { useState, useEffect } from 'react';
import {
  FlaskConical, Play, Loader2, TrendingDown, TrendingUp, ArrowRight, Zap,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import clsx from 'clsx';
import { api } from '../services/api.js';
import { fmtOMR, fmtNumber, fmtPct } from '../utils/format.js';
import { TIER_ORDER, TIER_HEX, TIER_BADGE, tierLabel } from '../utils/risk.js';

// Sliders that map 1:1 onto the backend Shock model.
const SLIDERS = [
  { key: 'dti_multiplier',     label: 'DTI Stress',        min: 1,   max: 3,    step: 0.05, fmt: (v) => `${v.toFixed(2)}×`, base: 1 },
  { key: 'rate_shock_bps',     label: 'Rate Shock',        min: 0,   max: 1000, step: 25,   fmt: (v) => `+${v} bps`,        base: 0 },
  { key: 'collateral_haircut', label: 'Collateral Haircut', min: 0,   max: 0.9,  step: 0.05, fmt: (v) => fmtPct(v * 100),    base: 0 },
  { key: 'income_shock',       label: 'Income Shock',      min: 0,   max: 0.9,  step: 0.05, fmt: (v) => fmtPct(v * 100),    base: 0 },
  { key: 'default_migration',  label: 'Default Migration', min: 0,   max: 0.5,  step: 0.05, fmt: (v) => fmtPct(v * 100),    base: 0 },
];

const EMPTY_SHOCK = {
  dti_multiplier: 1, rate_shock_bps: 0, collateral_haircut: 0, income_shock: 0, default_migration: 0,
};

function tierChartData(before, after) {
  return TIER_ORDER.map((t) => ({
    tier: tierLabel(t),
    key: t,
    before: before?.[t] ?? 0,
    after: after?.[t] ?? 0,
  }));
}

export default function StressTestView({ showToast }) {
  const [presets, setPresets] = useState({});
  const [shock, setShock]     = useState(EMPTY_SHOCK);
  const [scenarioName, setScenarioName] = useState('Custom Scenario');
  const [running, setRunning] = useState(false);
  const [result, setResult]   = useState(null);

  useEffect(() => {
    api.getStressPresets().then((d) => setPresets(d.presets ?? {})).catch(() => {});
  }, []);

  const applyPreset = (key) => {
    const p = presets[key];
    if (!p) return;
    setShock({ ...EMPTY_SHOCK, ...p.shock });
    setScenarioName(p.label ?? key);
  };

  const run = async () => {
    setRunning(true);
    try {
      const res = await api.runStressTest({ scenario_name: scenarioName, shock });
      setResult(res);
      showToast?.(`Scenario complete — ${res.downgrades} downgrades`, 'success');
    } catch (e) {
      showToast?.(`Stress test failed: ${e.message}`, 'error');
    } finally {
      setRunning(false);
    }
  };

  const elUp = result && result.expected_loss_delta_omr >= 0;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-extrabold tracking-tight text-gray-900 flex items-center gap-2">
          <FlaskConical className="w-6 h-6 text-violet-500" /> Model Stress Tests
        </h2>
        <p className="text-sm text-gray-400 mt-0.5">
          Apply a macro shock to the live book and re-score through the production engine · results are not persisted
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        {/* ── Scenario builder ─────────────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 space-y-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">Preset scenarios</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(presets).map(([key, p]) => (
                <button
                  key={key}
                  onClick={() => applyPreset(key)}
                  className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 text-gray-600 hover:border-violet-300 hover:text-violet-600 hover:bg-violet-50 transition-colors"
                >
                  {p.label ?? key}
                </button>
              ))}
            </div>
          </div>

          <div className="border-t border-gray-100 pt-4 space-y-4">
            {SLIDERS.map((s) => (
              <div key={s.key}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-medium text-gray-600">{s.label}</span>
                  <span className="font-mono font-semibold text-violet-600">{s.fmt(shock[s.key])}</span>
                </div>
                <input
                  type="range"
                  min={s.min} max={s.max} step={s.step}
                  value={shock[s.key]}
                  onChange={(e) => setShock((prev) => ({ ...prev, [s.key]: Number(e.target.value) }))}
                  className="w-full accent-violet-500"
                />
              </div>
            ))}
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={() => setShock(EMPTY_SHOCK)}
              className="px-3 py-2 text-sm font-medium rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50"
            >
              Reset
            </button>
            <button
              onClick={run}
              disabled={running}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg text-white transition-all active:scale-95 disabled:opacity-50"
              style={{ background: '#7c3aed' }}
            >
              {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {running ? 'Running…' : 'Run Scenario'}
            </button>
          </div>
        </div>

        {/* ── Results ──────────────────────────────────────────────────────── */}
        <div className="xl:col-span-2 space-y-5">
          {!result ? (
            <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-10 h-full flex flex-col items-center justify-center text-center">
              <Zap className="w-10 h-10 text-gray-200 mb-3" />
              <p className="text-gray-400 text-sm">Configure a scenario and run it to see portfolio migration.</p>
            </div>
          ) : (
            <>
              {/* Result KPIs */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">Downgrades</p>
                  <p className="text-2xl font-extrabold mt-1 text-gray-900">{fmtNumber(result.downgrades)}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{fmtPct(result.downgrade_pct)} of book</p>
                </div>
                <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">EL Before</p>
                  <p className="text-2xl font-extrabold mt-1 text-gray-900">{fmtOMR(result.expected_loss_before_omr)}</p>
                </div>
                <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">EL After</p>
                  <p className="text-2xl font-extrabold mt-1" style={{ color: elUp ? '#dc2626' : '#16a34a' }}>
                    {fmtOMR(result.expected_loss_after_omr)}
                  </p>
                </div>
                <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">EL Change</p>
                  <p className="text-2xl font-extrabold mt-1 flex items-center gap-1" style={{ color: elUp ? '#dc2626' : '#16a34a' }}>
                    {elUp ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
                    {fmtPct(result.expected_loss_increase_pct)}
                  </p>
                </div>
              </div>

              {/* Migration chart */}
              <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
                <p className="text-sm font-bold text-gray-700 mb-3">Tier Distribution — Before vs After</p>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={tierChartData(result.tier_distribution_before, result.tier_distribution_after)}>
                    <XAxis dataKey="tier" tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                    <Tooltip cursor={{ fill: 'rgba(0,0,0,0.03)' }} />
                    <Bar dataKey="before" name="Before" radius={[4, 4, 0, 0]} fill="#cbd5e1" />
                    <Bar dataKey="after" name="After" radius={[4, 4, 0, 0]}>
                      {tierChartData(result.tier_distribution_before, result.tier_distribution_after).map((d) => (
                        <Cell key={d.key} fill={TIER_HEX[d.key]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Top migrations */}
              <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
                <p className="text-sm font-bold text-gray-700 px-5 pt-4 pb-2">Worst-Hit Clients</p>
                {result.top_migrations.length === 0 ? (
                  <p className="px-5 pb-5 text-sm text-gray-400">No tier downgrades under this scenario.</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs font-semibold uppercase tracking-wider text-gray-400 border-b border-gray-100">
                        <th className="px-5 py-2">Client</th>
                        <th className="px-5 py-2">Migration</th>
                        <th className="px-5 py-2 text-right">Score Δ</th>
                        <th className="px-5 py-2 text-right">Exposure</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.top_migrations.slice(0, 12).map((m) => (
                        <tr key={m.client_id} className="border-b border-gray-50 hover:bg-gray-50/60">
                          <td className="px-5 py-2.5 font-medium text-gray-800">{m.client_name}</td>
                          <td className="px-5 py-2.5">
                            <span className="inline-flex items-center gap-1.5">
                              <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold border', TIER_BADGE[m.from_tier])}>{tierLabel(m.from_tier)}</span>
                              <ArrowRight className="w-3 h-3 text-gray-300" />
                              <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold border', TIER_BADGE[m.to_tier])}>{tierLabel(m.to_tier)}</span>
                            </span>
                          </td>
                          <td className="px-5 py-2.5 text-right font-mono font-semibold text-red-600">+{fmtNumber(m.score_delta, 1)}</td>
                          <td className="px-5 py-2.5 text-right font-mono text-gray-600">{fmtOMR(m.outstanding_debt)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
