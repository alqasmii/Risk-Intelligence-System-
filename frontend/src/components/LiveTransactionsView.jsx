import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Activity, ArrowDownLeft, ArrowUpRight, Banknote, Radio, Pause, Play,
  Search, Globe, AlertTriangle,
} from 'lucide-react';
import clsx from 'clsx';
import { api } from '../services/api.js';
import { fmtOMR, fmtOMRFull, fmtNumber, fmtPct, fmtTimeAgo } from '../utils/format.js';

// ── Type + risk-flag styling ─────────────────────────────────────────────────
const TYPE_STYLE = {
  CREDIT:   { icon: ArrowDownLeft, cls: 'text-emerald-600 bg-emerald-50' },
  DEBIT:    { icon: ArrowUpRight,  cls: 'text-slate-600 bg-slate-100'   },
  WIRE:     { icon: Radio,         cls: 'text-indigo-600 bg-indigo-50'  },
  CASH:     { icon: Banknote,      cls: 'text-amber-600 bg-amber-50'    },
  REVERSAL: { icon: ArrowUpRight,  cls: 'text-rose-600 bg-rose-50'      },
};

const FLAG_STYLE = {
  WIRE:         'bg-indigo-50 text-indigo-700 border-indigo-200',
  LARGE_CASH:   'bg-red-50 text-red-700 border-red-200',
  HIGH_VALUE:   'bg-amber-50 text-amber-700 border-amber-200',
  CROSS_BORDER: 'bg-sky-50 text-sky-700 border-sky-200',
};
const FLAG_LABEL = {
  WIRE: 'Wire', LARGE_CASH: 'Large Cash', HIGH_VALUE: 'High Value', CROSS_BORDER: 'Cross-Border',
};

const TYPES = ['CREDIT', 'DEBIT', 'WIRE', 'CASH', 'REVERSAL'];

function StatCard({ label, value, sub, accent }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">{label}</p>
      <p className="text-2xl font-extrabold mt-1" style={{ color: accent ?? '#0f172a' }}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function LiveTransactionsView() {
  const [items, setItems]   = useState([]);
  const [stats, setStats]   = useState(null);
  const [total, setTotal]   = useState(0);
  const [loading, setLoading] = useState(true);
  const [live, setLive]     = useState(true);
  const [typeFilter, setTypeFilter] = useState('');
  const [highRiskOnly, setHighRiskOnly] = useState(false);
  const [search, setSearch] = useState('');
  const [flash, setFlash]   = useState(new Set());
  const prevIds = useRef(new Set());

  const load = useCallback(async () => {
    try {
      const params = { limit: 40 };
      if (typeFilter) params.tx_type = typeFilter;
      if (highRiskOnly) params.high_risk_only = true;
      const [feed, s] = await Promise.all([
        api.getTransactions(params),
        api.getTransactionStats({ window_hours: 720 }),
      ]);
      const rows = feed.items ?? [];
      // Flash rows that are new since the last poll (live-feed affordance).
      const newIds = new Set();
      for (const r of rows) if (!prevIds.current.has(r.id)) newIds.add(r.id);
      if (prevIds.current.size) setFlash(newIds);
      prevIds.current = new Set(rows.map((r) => r.id));
      setItems(rows);
      setTotal(feed.total ?? rows.length);
      setStats(s);
    } catch {
      /* keep last-known data on transient error */
    } finally {
      setLoading(false);
    }
  }, [typeFilter, highRiskOnly]);

  useEffect(() => { load(); }, [load]);

  // Live polling — pauses when the user toggles off.
  useEffect(() => {
    if (!live) return undefined;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [live, load]);

  const filtered = search
    ? items.filter((t) =>
        t.client_name.toLowerCase().includes(search.toLowerCase()) ||
        (t.location_city ?? '').toLowerCase().includes(search.toLowerCase()))
    : items;

  return (
    <div className="space-y-5">
      {/* ── Header row ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold tracking-tight text-gray-900 flex items-center gap-2">
            <Activity className="w-6 h-6 text-indigo-500" /> Live Transactions
          </h2>
          <p className="text-sm text-gray-400 mt-0.5">
            Real-time transaction monitoring feed · newest first
          </p>
        </div>
        <button
          onClick={() => setLive((v) => !v)}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg border transition-all active:scale-95',
            live
              ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
              : 'bg-gray-50 border-gray-200 text-gray-500',
          )}
        >
          {live
            ? <><span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" /> Live</>
            : <><Pause className="w-3.5 h-3.5" /> Paused</>}
        </button>
      </div>

      {/* ── KPI strip ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Volume (30d)" value={fmtNumber(stats?.total_count)} sub={`${fmtNumber(total)} total on file`} />
        <StatCard label="Value (30d)"  value={fmtOMR(stats?.total_value_omr)} accent="#4f46e5" />
        <StatCard label="Wire Share"   value={fmtPct(stats?.wire_pct)} sub={`${fmtNumber(stats?.wire_count)} wires`} accent="#0ea5e9" />
        <StatCard label="Cross-Border" value={fmtNumber(stats?.cross_border_count)} sub={fmtPct(stats?.cross_border_pct)} accent="#f59e0b" />
      </div>

      {/* ── Filters ────────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-3 flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-gray-300 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search client or city…"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-200"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="px-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white"
        >
          <option value="">All types</option>
          {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button
          onClick={() => setHighRiskOnly((v) => !v)}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border transition-colors',
            highRiskOnly
              ? 'bg-red-50 border-red-200 text-red-700'
              : 'bg-white border-gray-200 text-gray-500 hover:bg-gray-50',
          )}
        >
          <AlertTriangle className="w-3.5 h-3.5" /> High-risk only
        </button>
      </div>

      {/* ── Feed table ─────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs font-semibold uppercase tracking-wider text-gray-400 border-b border-gray-100">
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Client</th>
              <th className="px-4 py-3 text-right">Amount</th>
              <th className="px-4 py-3">Location</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Flag</th>
              <th className="px-4 py-3 text-right">Time</th>
            </tr>
          </thead>
          <tbody>
            {loading && !filtered.length ? (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-gray-400">Loading feed…</td></tr>
            ) : !filtered.length ? (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-gray-400">No transactions match your filters.</td></tr>
            ) : filtered.map((t) => {
              const ts = TYPE_STYLE[t.transaction_type] ?? TYPE_STYLE.DEBIT;
              const Icon = ts.icon;
              return (
                <tr
                  key={t.id}
                  className={clsx(
                    'border-b border-gray-50 hover:bg-gray-50/60 transition-colors',
                    flash.has(t.id) && 'animate-[pulse_1s_ease-in-out]',
                  )}
                  style={flash.has(t.id) ? { background: 'rgba(79,70,229,0.05)' } : {}}
                >
                  <td className="px-4 py-3">
                    <span className={clsx('inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-semibold', ts.cls)}>
                      <Icon className="w-3.5 h-3.5" /> {t.transaction_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-800">{t.client_name}</td>
                  <td className="px-4 py-3 text-right font-mono font-semibold text-gray-900" title={fmtOMRFull(t.amount)}>
                    {fmtOMR(t.amount)}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    <span className="inline-flex items-center gap-1">
                      <Globe className="w-3 h-3 text-gray-300" />
                      {t.location_city ? `${t.location_city}, ${t.location_country}` : (t.location_country ?? '—')}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{t.merchant_category ?? '—'}</td>
                  <td className="px-4 py-3">
                    {t.risk_flag
                      ? <span className={clsx('px-2 py-0.5 rounded-full text-xs font-semibold border', FLAG_STYLE[t.risk_flag])}>{FLAG_LABEL[t.risk_flag]}</span>
                      : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-400 whitespace-nowrap">{fmtTimeAgo(t.timestamp)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
