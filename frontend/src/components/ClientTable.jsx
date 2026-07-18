import { useState, useMemo } from 'react';
import { Search, ChevronLeft, ChevronRight, ShieldAlert, Scan, ArrowUpDown } from 'lucide-react';
import { api } from '../services/api.js';
import { fmtOMR } from '../utils/format.js';
import clsx from 'clsx';

const TIER_STYLE = {
  CRITICAL: 'bg-red-100 text-red-700 border-red-200',
  HIGH:     'bg-orange-100 text-orange-700 border-orange-200',
  MEDIUM:   'bg-amber-100 text-amber-700 border-amber-200',
  LOW:      'bg-green-100 text-green-700 border-green-200',
};

const scoreColor = s => s >= 75 ? '#dc2626' : s >= 50 ? '#ea580c' : s >= 25 ? '#d97706' : '#16a34a';
const scoreTextCls = s => s >= 75 ? 'text-red-600' : s >= 50 ? 'text-orange-500' : s >= 25 ? 'text-amber-500' : 'text-green-600';

const PAGE_SIZE = 10;

// ── sub-components ───────────────────────────────────────────────────────────
function SortBtn({ k, current, dir, onChange, children }) {
  return (
    <button
      className="flex items-center gap-1 hover:text-[#1e293b] transition-colors"
      onClick={() => onChange(k)}
    >
      {children}
      <ArrowUpDown className={clsx('w-3 h-3 flex-shrink-0', current === k ? 'text-[#1e293b]' : 'text-gray-300')} />
    </button>
  );
}

function SkeletonRow() {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: 7 }).map((_, i) => (
        <td key={i} className="px-4 py-4"><div className="h-4 bg-gray-100 rounded w-4/5" /></td>
      ))}
    </tr>
  );
}

// ── main ─────────────────────────────────────────────────────────────────────
export default function ClientTable({ clients, loading, showToast, onRefresh }) {
  const [search,   setSearch]   = useState('');
  const [page,     setPage]     = useState(1);
  const [sortKey,  setSortKey]  = useState('composite_score');
  const [sortDir,  setSortDir]  = useState('desc');
  const [freezing, setFreezing] = useState(null);

  const handleSort = key => {
    if (sortKey === key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return (clients ?? [])
      .filter(c =>
        !q ||
        c.client_id.toLowerCase().includes(q) ||
        (c.client_name ?? '').toLowerCase().includes(q) ||
        c.risk_tier.toLowerCase().includes(q),
      )
      .sort((a, b) => {
        const av = a[sortKey] ?? 0, bv = b[sortKey] ?? 0;
        return sortDir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
      });
  }, [clients, search, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageData   = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleFreeze = async client => {
    setFreezing(client.client_id);
    await new Promise(r => setTimeout(r, 800)); // simulate network call
    showToast(`Account ${client.client_id.slice(0, 10)}… flagged for freeze — compliance notified`, 'success');
    setFreezing(null);
  };

  const handleScan = async client => {
    try {
      showToast(`Running deep scan on ${client.client_id.slice(0, 10)}…`, 'info');
      await api.scanAnomalies();
      showToast(`Deep scan complete — results refreshed`, 'success');
      onRefresh();
    } catch (e) {
      showToast(`Scan failed: ${e.message}`, 'error');
    }
  };

  const sp = { current: sortKey, dir: sortDir, onChange: handleSort };

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      {/* ── Table toolbar ── */}
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-sm font-bold text-gray-900">High-Risk Client Monitor</h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {filtered.length} clients · showing {pageData.length} records
          </p>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
            placeholder="Search clients…"
            className="pl-8 pr-4 py-2 text-xs border border-gray-200 rounded-lg w-56 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-[#1e293b]"
          />
        </div>
      </div>

      {/* ── Table ── */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-100">
              <th className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Client</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <SortBtn k="risk_tier" {...sp}>Risk Tier</SortBtn>
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <SortBtn k="composite_score" {...sp}>Risk Score</SortBtn>
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <SortBtn k="total_outstanding_debt" {...sp}>Exposure (USD)</SortBtn>
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <SortBtn k="open_anomaly_count" {...sp}>Anomalies</SortBtn>
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">KYC / PEP</th>
              <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading
              ? Array.from({ length: 7 }).map((_, i) => <SkeletonRow key={i} />)
              : !pageData.length
              ? (
                <tr>
                  <td colSpan={7} className="text-center py-14 text-sm text-gray-400">
                    No clients — click <span className="font-semibold text-[#1e293b]">Run Pipeline</span> first
                  </td>
                </tr>
              )
              : pageData.map(client => {
                  const score = client.composite_score ?? 0;
                  return (
                    <tr key={client.client_id} className="hover:bg-[#faf8fc] transition-colors">
                      {/* ── Client ── */}
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2.5">
                          <div
                            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
                            style={{ background: '#1e293b' }}
                          >
                            {(client.client_name ?? client.client_id)[0]?.toUpperCase()}
                          </div>
                          <div>
                            <p className="text-xs font-bold text-gray-800 font-mono">
                              {client.client_id.slice(0, 13)}
                            </p>
                            <p className="text-xs text-gray-400">{client.client_type}</p>
                          </div>
                        </div>
                      </td>

                      {/* ── Tier ── */}
                      <td className="px-4 py-3.5">
                        <span className={clsx('text-xs font-bold px-2.5 py-1 rounded-full border', TIER_STYLE[client.risk_tier] ?? 'bg-gray-100 text-gray-600')}>
                          {client.risk_tier}
                        </span>
                      </td>

                      {/* ── Score ── */}
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-2.5">
                          <span className={clsx('text-sm font-extrabold tabular-nums w-10', scoreTextCls(score))}>
                            {score.toFixed(1)}
                          </span>
                          <div className="w-20 bg-gray-100 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="h-full rounded-full"
                              style={{ width: `${Math.min(score, 100)}%`, background: scoreColor(score) }}
                            />
                          </div>
                        </div>
                      </td>

                      {/* ── Exposure ── */}
                      <td className="px-4 py-3.5">
                        <p className="text-xs font-bold text-gray-900 tabular-nums">{fmtOMR(client.total_outstanding_debt)}</p>
                        <p className="text-xs text-gray-400">{client.active_loans_count ?? 0} loans</p>
                      </td>

                      {/* ── Anomalies ── */}
                      <td className="px-4 py-3.5">
                        {client.open_anomaly_count > 0 ? (
                          <div className="flex items-center gap-1.5 text-xs">
                            <span className="font-bold text-red-600">{client.open_anomaly_count}</span>
                            <span className="text-gray-400">open</span>
                            {client.critical_anomaly_count > 0 && (
                              <span className="text-red-500 font-semibold">
                                ({client.critical_anomaly_count}⚡)
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-green-600 font-semibold">Clean</span>
                        )}
                      </td>

                      {/* ── KYC / PEP ── */}
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className={clsx(
                            'text-xs px-2 py-0.5 rounded-full font-medium',
                            client.kyc_status === 'VERIFIED'
                              ? 'bg-green-50 text-green-700'
                              : 'bg-amber-50 text-amber-700',
                          )}>
                            {client.kyc_status}
                          </span>
                          {client.is_pep && (
                            <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-bold">
                              PEP
                            </span>
                          )}
                        </div>
                      </td>

                      {/* ── Actions ── */}
                      <td className="px-4 py-3.5">
                        <div className="flex items-center justify-center gap-2">
                          <button
                            onClick={() => handleFreeze(client)}
                            disabled={freezing === client.client_id}
                            title="Freeze Account"
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg text-white transition-all active:scale-95 disabled:opacity-50"
                            style={{ background: '#dc2626' }}
                          >
                            <ShieldAlert className="w-3 h-3" />
                            {freezing === client.client_id ? '…' : 'Freeze'}
                          </button>
                          <button
                            onClick={() => handleScan(client)}
                            title="Run Deep Scan"
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all active:scale-95 hover:bg-blue-50"
                            style={{ color: '#1e293b', borderColor: '#c4b5d4' }}
                          >
                            <Scan className="w-3 h-3" />
                            Scan
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ── */}
      {filtered.length > PAGE_SIZE && (
        <div className="px-6 py-3 border-t border-gray-100 flex items-center justify-between">
          <p className="text-xs text-gray-400">
            Page {page} of {totalPages} · {filtered.length} total
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-30 transition-colors"
            >
              <ChevronLeft className="w-4 h-4 text-gray-600" />
            </button>
            {Array.from({ length: Math.min(totalPages, 7) }).map((_, i) => {
              const pg = i + 1;
              return (
                <button
                  key={pg}
                  onClick={() => setPage(pg)}
                  className={clsx(
                    'w-7 h-7 rounded-lg text-xs font-semibold transition-colors',
                    page === pg ? 'text-white' : 'text-gray-600 hover:bg-gray-100',
                  )}
                  style={page === pg ? { background: '#1e293b' } : {}}
                >
                  {pg}
                </button>
              );
            })}
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-30 transition-colors"
            >
              <ChevronRight className="w-4 h-4 text-gray-600" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
