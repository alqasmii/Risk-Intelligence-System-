import { useState, useEffect } from 'react';
import {
  PieChart as PieIcon, TrendingUp, Layers, Globe2, Wallet, AlertOctagon,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  LineChart, Line, PieChart, Pie, CartesianGrid,
} from 'recharts';
import { api } from '../services/api.js';
import { fmtOMR, fmtNumber, fmtPct } from '../utils/format.js';
import { TIER_ORDER, TIER_HEX, tierLabel } from '../utils/risk.js';

const AGING_HEX = { CURRENT: '#10b981', '1-29': '#eab308', '30-89': '#f97316', '90+': '#ef4444' };
const SECTOR_HEX = ['#4f46e5', '#0ea5e9', '#10b981', '#f59e0b', '#f97316', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#64748b'];

function KpiCard({ icon: Icon, label, value, sub, accent }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
      <div className="flex items-center gap-2 text-gray-400">
        <Icon className="w-4 h-4" />
        <p className="text-xs font-semibold uppercase tracking-wider">{label}</p>
      </div>
      <p className="text-2xl font-extrabold mt-1.5" style={{ color: accent ?? '#0f172a' }}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function Panel({ title, icon: Icon, children }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
      <p className="text-sm font-bold text-gray-700 mb-4 flex items-center gap-2">
        {Icon && <Icon className="w-4 h-4 text-gray-400" />} {title}
      </p>
      {children}
    </div>
  );
}

export default function PortfolioAnalyticsView() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getPortfolioAnalytics()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading analytics…</div>;
  }
  if (!data) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Analytics unavailable.</div>;
  }

  const sectorData = (data.exposure_by_sector ?? []).map((s, i) => ({ ...s, hex: SECTOR_HEX[i % SECTOR_HEX.length] }));
  const agingData = (data.delinquency_aging ?? []).map((a) => ({ ...a, hex: AGING_HEX[a.bucket] ?? '#94a3b8' }));
  const elByTier = (data.expected_loss_by_tier ?? []).map((e) => ({ ...e, label: tierLabel(e.tier), hex: TIER_HEX[e.tier] }));

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-extrabold tracking-tight text-gray-900 flex items-center gap-2">
          <PieIcon className="w-6 h-6 text-sky-500" /> Portfolio Analytics
        </h2>
        <p className="text-sm text-gray-400 mt-0.5">
          Concentration, quality, and expected credit loss across the book · all figures in OMR
        </p>
      </div>

      {/* ── KPI strip ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard icon={Wallet}     label="Total Exposure" value={fmtOMR(data.total_ead_omr)} sub={`${fmtNumber(data.total_loans)} facilities`} />
        <KpiCard icon={AlertOctagon} label="Expected Loss" value={fmtOMR(data.expected_loss_omr)} accent="#dc2626" sub="PD × LGD × EAD" />
        <KpiCard icon={TrendingUp} label="EL Ratio" value={fmtPct(data.expected_loss_ratio_pct)} accent="#f59e0b" />
        <KpiCard icon={Layers}     label="Clients" value={fmtNumber(data.total_clients)} sub="under management" />
      </div>

      {/* ── Row 1: sector + country ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <Panel title="Exposure by Sector" icon={Layers}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={sectorData} layout="vertical" margin={{ left: 20 }}>
              <XAxis type="number" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false}
                     tickFormatter={(v) => fmtOMR(v)} />
              <YAxis type="category" dataKey="label" width={130} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
              <Tooltip formatter={(v) => fmtOMR(v)} cursor={{ fill: 'rgba(0,0,0,0.03)' }} />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {sectorData.map((s) => <Cell key={s.label} fill={s.hex} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Exposure by Country" icon={Globe2}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data.exposure_by_country ?? []}>
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} tickFormatter={(v) => fmtOMR(v)} />
              <Tooltip formatter={(v) => fmtOMR(v)} cursor={{ fill: 'rgba(0,0,0,0.03)' }} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]} fill="#0ea5e9" />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      {/* ── Row 2: aging + EL by tier + loan mix ───────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <Panel title="Delinquency Aging" icon={AlertOctagon}>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={agingData} dataKey="balance" nameKey="bucket" cx="50%" cy="50%" outerRadius={80} innerRadius={45}>
                {agingData.map((a) => <Cell key={a.bucket} fill={a.hex} />)}
              </Pie>
              <Tooltip formatter={(v) => fmtOMR(v)} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-2 justify-center mt-2">
            {agingData.map((a) => (
              <span key={a.bucket} className="flex items-center gap-1 text-xs text-gray-500">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: a.hex }} /> {a.bucket}
              </span>
            ))}
          </div>
        </Panel>

        <Panel title="Expected Loss by Tier" icon={AlertOctagon}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={elByTier}>
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} tickFormatter={(v) => fmtOMR(v)} />
              <Tooltip formatter={(v) => fmtOMR(v)} cursor={{ fill: 'rgba(0,0,0,0.03)' }} />
              <Bar dataKey="expected_loss" radius={[4, 4, 0, 0]}>
                {elByTier.map((e) => <Cell key={e.tier} fill={e.hex} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Loan Type Mix" icon={Layers}>
          <div className="space-y-3 pt-2">
            {(data.loan_type_mix ?? []).map((l, i) => {
              const max = Math.max(...(data.loan_type_mix ?? []).map((x) => x.balance), 1);
              return (
                <div key={l.label}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="font-medium text-gray-600">{l.label}</span>
                    <span className="font-mono text-gray-500">{fmtOMR(l.balance)} · {l.count}</span>
                  </div>
                  <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${(l.balance / max) * 100}%`, background: SECTOR_HEX[i % SECTOR_HEX.length] }} />
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>

      {/* ── Row 3: score trend ─────────────────────────────────────────────── */}
      <Panel title="Portfolio Risk-Score Trend" icon={TrendingUp}>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data.score_trend ?? []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
            <Tooltip />
            <Line type="monotone" dataKey="avg_score" name="Avg score" stroke="#4f46e5" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </Panel>
    </div>
  );
}
