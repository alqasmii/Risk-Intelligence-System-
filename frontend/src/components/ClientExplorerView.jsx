import { useState, useEffect, useCallback } from 'react';
import {
  Users, Search, X, Building2, User, ShieldAlert, ArrowUpDown, Loader2,
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip,
} from 'recharts';
import clsx from 'clsx';
import { api } from '../services/api.js';
import { fmtOMR, fmtOMRFull, fmtNumber, fmtDate, fmtDateTime, fmtPct } from '../utils/format.js';
import { TIER_BADGE, TIER_HEX, tierLabel, scoreHex } from '../utils/risk.js';

const KYC_STYLE = {
  VERIFIED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  PENDING:  'bg-amber-50 text-amber-700 border-amber-200',
  EXPIRED:  'bg-orange-50 text-orange-700 border-orange-200',
  REJECTED: 'bg-red-50 text-red-700 border-red-200',
};

const SORTS = [
  { id: 'score_desc', label: 'Risk ↓' },
  { id: 'score_asc',  label: 'Risk ↑' },
  { id: 'debt_desc',  label: 'Exposure ↓' },
  { id: 'name',       label: 'Name' },
];

function Badge({ children, cls }) {
  return <span className={clsx('px-2 py-0.5 rounded-full border text-xs font-semibold', cls)}>{children}</span>;
}

// ── Detail drawer ────────────────────────────────────────────────────────────
function ClientDrawer({ clientId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.getClient360(clientId)
      .then((d) => { if (alive) setData(d); })
      .catch(() => {})
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [clientId]);

  const score = data?.latest_score;
  const components = score ? [
    { label: 'Credit History', value: score.credit_history_score, hex: '#4f46e5' },
    { label: 'Behavioural', value: score.behavioral_score, hex: '#0ea5e9' },
    { label: 'Exposure', value: score.exposure_score, hex: '#f59e0b' },
  ] : [];

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative w-full max-w-xl bg-[#f8fafc] h-full overflow-y-auto shadow-2xl animate-[slideIn_0.2s_ease-out]">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-100 px-5 py-4 flex items-center justify-between z-10">
          <p className="font-bold text-gray-800">Client 360°</p>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64 text-gray-400">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading…
          </div>
        ) : !data ? (
          <div className="p-6 text-gray-400">Client not found.</div>
        ) : (
          <div className="p-5 space-y-5">
            {/* Identity */}
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-lg font-extrabold text-gray-900">{data.client.client_name}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{data.client.client_type} · {data.client.country_of_residence ?? '—'}{data.client.industry_sector ? ` · ${data.client.industry_sector}` : ''}</p>
                </div>
                {score && (
                  <div className="text-right">
                    <p className="text-3xl font-extrabold" style={{ color: scoreHex(score.composite_score) }}>
                      {fmtNumber(score.composite_score, 1)}
                    </p>
                    <Badge cls={TIER_BADGE[score.risk_tier]}>{tierLabel(score.risk_tier)}</Badge>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                {data.client.is_pep && <Badge cls="bg-purple-50 text-purple-700 border-purple-200">PEP</Badge>}
                <Badge cls={KYC_STYLE[data.client.kyc_status] ?? 'bg-gray-50 text-gray-600 border-gray-200'}>KYC: {data.client.kyc_status}</Badge>
                {data.client.external_credit_score != null && <Badge cls="bg-gray-50 text-gray-600 border-gray-200">Bureau {data.client.external_credit_score}</Badge>}
              </div>
            </div>

            {/* Score components */}
            {score && (
              <div className="bg-white rounded-xl border border-gray-100 p-5">
                <p className="text-sm font-bold text-gray-700 mb-3">Score Breakdown</p>
                <div className="space-y-3">
                  {components.map((c) => (
                    <div key={c.label}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-600">{c.label}</span>
                        <span className="font-mono font-semibold text-gray-800">{fmtNumber(c.value, 1)}</span>
                      </div>
                      <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${Math.min(c.value, 100)}%`, background: c.hex }} />
                      </div>
                    </div>
                  ))}
                </div>
                {(score.pep_adjustment > 0 || score.kyc_adjustment > 0) && (
                  <p className="text-xs text-gray-400 mt-3">
                    Compliance add-ons: PEP +{fmtNumber(score.pep_adjustment, 1)}, KYC +{fmtNumber(score.kyc_adjustment, 1)}
                  </p>
                )}
              </div>
            )}

            {/* Score history */}
            {data.score_history?.length > 1 && (
              <div className="bg-white rounded-xl border border-gray-100 p-5">
                <p className="text-sm font-bold text-gray-700 mb-3">Score History</p>
                <ResponsiveContainer width="100%" height={140}>
                  <LineChart data={data.score_history}>
                    <XAxis dataKey="scored_at" hide />
                    <YAxis domain={[0, 100]} width={28} tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
                    <Tooltip labelFormatter={(v) => fmtDateTime(v)} formatter={(v) => [fmtNumber(v, 1), 'Score']} />
                    <Line type="monotone" dataKey="composite_score" stroke="#4f46e5" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Loans */}
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <p className="text-sm font-bold text-gray-700 mb-3">Loan Facilities ({data.loans.length})</p>
              {data.loans.length === 0 ? <p className="text-xs text-gray-400">No active facilities.</p> : (
                <div className="space-y-2">
                  {data.loans.map((l) => (
                    <div key={l.id} className="flex items-center justify-between text-sm border-b border-gray-50 pb-2 last:border-0">
                      <div>
                        <span className="font-medium text-gray-700">{l.loan_type}</span>
                        <span className="text-xs text-gray-400 ml-2">{l.status}{l.days_past_due ? ` · ${l.days_past_due}dpd` : ''}</span>
                      </div>
                      <div className="text-right">
                        <p className="font-mono text-gray-800">{fmtOMR(l.outstanding_balance)}</p>
                        <p className="text-xs text-gray-400">{fmtPct(l.interest_rate)} · {l.collateral_type ?? 'unsecured'}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Anomalies */}
            {data.anomalies?.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-100 p-5">
                <p className="text-sm font-bold text-gray-700 mb-3 flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4 text-red-400" /> Open Anomalies ({data.anomalies.length})
                </p>
                <div className="space-y-2">
                  {data.anomalies.map((a) => (
                    <div key={a.id} className="text-sm border-b border-gray-50 pb-2 last:border-0">
                      <div className="flex justify-between">
                        <span className="font-medium text-gray-700">{a.type}</span>
                        <Badge cls={a.severity === 'CRITICAL' ? TIER_BADGE.CRITICAL : TIER_BADGE.HIGH}>{a.severity}</Badge>
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5">{a.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recent transactions */}
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <p className="text-sm font-bold text-gray-700 mb-3">Recent Transactions</p>
              {data.recent_transactions.length === 0 ? <p className="text-xs text-gray-400">None.</p> : (
                <div className="space-y-1.5">
                  {data.recent_transactions.map((t) => (
                    <div key={t.id} className="flex items-center justify-between text-xs">
                      <span className="text-gray-500">{t.transaction_type} · {t.location_country ?? '—'}</span>
                      <span className="font-mono text-gray-700" title={fmtOMRFull(t.amount)}>{fmtOMR(t.amount)}</span>
                      <span className="text-gray-300">{fmtDate(t.timestamp)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main explorer ────────────────────────────────────────────────────────────
export default function ClientExplorerView() {
  const [rows, setRows]     = useState([]);
  const [total, setTotal]   = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [typeF, setTypeF]   = useState('');
  const [pepOnly, setPepOnly] = useState(false);
  const [sort, setSort]     = useState('score_desc');
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 100, sort };
      if (search) params.q = search;
      if (typeF) params.client_type = typeF;
      if (pepOnly) params.is_pep = true;
      const d = await api.getClients(params);
      setRows(d.items ?? []);
      setTotal(d.total ?? 0);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [search, typeF, pepOnly, sort]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-extrabold tracking-tight text-gray-900 flex items-center gap-2">
          <Users className="w-6 h-6 text-blue-500" /> Client Explorer
        </h2>
        <p className="text-sm text-gray-400 mt-0.5">
          Searchable client directory · {fmtNumber(total)} clients · click a row for the 360° view
        </p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-3 flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-gray-300 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or ID…"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-200"
          />
        </div>
        <select value={typeF} onChange={(e) => setTypeF(e.target.value)}
                className="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-blue-200">
          <option value="">All types</option>
          <option value="RETAIL">Retail</option>
          <option value="CORPORATE">Corporate</option>
        </select>
        <button
          onClick={() => setPepOnly((v) => !v)}
          className={clsx('flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border transition-colors',
            pepOnly ? 'bg-purple-50 border-purple-200 text-purple-700' : 'bg-white border-gray-200 text-gray-500 hover:bg-gray-50')}
        >
          <ShieldAlert className="w-3.5 h-3.5" /> PEP only
        </button>
        <select value={sort} onChange={(e) => setSort(e.target.value)}
                className="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white focus:outline-none focus:ring-2 focus:ring-blue-200">
          {SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs font-semibold uppercase tracking-wider text-gray-400 border-b border-gray-100">
              <th className="px-4 py-3">Client</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">KYC</th>
              <th className="px-4 py-3 text-right">Score</th>
              <th className="px-4 py-3">Tier</th>
              <th className="px-4 py-3 text-right">Exposure</th>
            </tr>
          </thead>
          <tbody>
            {loading && !rows.length ? (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-400">Loading clients…</td></tr>
            ) : !rows.length ? (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-400">No clients match your filters.</td></tr>
            ) : rows.map((c) => (
              <tr
                key={c.client_id}
                onClick={() => setSelected(c.client_id)}
                className="border-b border-gray-50 hover:bg-blue-50/40 cursor-pointer transition-colors"
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {c.client_type === 'CORPORATE'
                      ? <Building2 className="w-4 h-4 text-gray-300" />
                      : <User className="w-4 h-4 text-gray-300" />}
                    <div>
                      <p className="font-medium text-gray-800">{c.client_name}</p>
                      {c.is_pep && <span className="text-xs text-purple-500 font-semibold">PEP</span>}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-gray-500">{c.client_type}</td>
                <td className="px-4 py-3">
                  <Badge cls={KYC_STYLE[c.kyc_status] ?? 'bg-gray-50 text-gray-600 border-gray-200'}>{c.kyc_status}</Badge>
                </td>
                <td className="px-4 py-3 text-right font-mono font-semibold" style={{ color: scoreHex(c.composite_score) }}>
                  {c.composite_score != null ? fmtNumber(c.composite_score, 1) : '—'}
                </td>
                <td className="px-4 py-3">
                  {c.risk_tier ? <Badge cls={TIER_BADGE[c.risk_tier]}>{tierLabel(c.risk_tier)}</Badge> : <span className="text-gray-300">—</span>}
                </td>
                <td className="px-4 py-3 text-right font-mono text-gray-600">
                  {c.total_outstanding_debt != null ? fmtOMR(c.total_outstanding_debt) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && <ClientDrawer clientId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
