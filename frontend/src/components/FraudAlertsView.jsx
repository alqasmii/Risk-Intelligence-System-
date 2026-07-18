import { useState, useMemo } from 'react';
import { CheckCircle, Clock, Search, X } from 'lucide-react';
import { api } from '../services/api.js';
import { fmtOMRFull } from '../utils/format.js';
import clsx from 'clsx';

// ── styles ───────────────────────────────────────────────────────────────────
const SEV_STYLE = {
  CRITICAL: 'bg-red-100 text-red-700 border-red-200',
  HIGH:     'bg-orange-100 text-orange-700 border-orange-200',
  MEDIUM:   'bg-amber-100 text-amber-700 border-amber-200',
  LOW:      'bg-sky-100 text-sky-700 border-sky-200',
};

const SEV_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

function ago(dateStr) {
  const d = (Date.now() - new Date(dateStr)) / 1000;
  if (d < 60)    return `${Math.floor(d)}s ago`;
  if (d < 3600)  return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return new Date(dateStr).toLocaleDateString();
}

// ── Resolve modal ─────────────────────────────────────────────────────────────
function ResolveModal({ flag, onClose, onConfirm, confirming }) {
  const [note, setNote] = useState('');
  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-green-100 flex items-center justify-center">
            <CheckCircle className="w-5 h-5 text-green-600" />
          </div>
          <div>
            <h3 className="font-extrabold text-gray-900">Resolve Flag</h3>
            <p className="text-xs text-gray-500 font-mono">
              {flag.rule_triggered} · <span className={clsx('font-bold', SEV_STYLE[flag.severity]?.split(' ')[1])}>{flag.severity}</span>
            </p>
          </div>
          <button className="ml-auto p-1 text-gray-400 hover:text-gray-700" onClick={onClose}>
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-sm text-gray-600 mb-4 leading-relaxed">{flag.description}</p>

        <label className="block text-xs font-semibold text-gray-700 mb-1.5">
          Analyst Resolution Note <span className="text-red-500">*</span>
          <span className="font-normal text-gray-400 ml-1">(required for audit trail)</span>
        </label>
        <textarea
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="e.g. Reviewed transaction history — confirmed legitimate activity from travel..."
          className="w-full border border-gray-200 rounded-xl p-3 text-sm resize-none h-24 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-[#1e293b]"
        />

        <div className="flex gap-3 mt-4">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 text-sm font-semibold text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(note)}
            disabled={confirming || !note.trim()}
            className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold text-white transition-all disabled:opacity-50"
            style={{ background: '#16a34a' }}
          >
            {confirming ? 'Submitting…' : 'Confirm Resolution'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── main ─────────────────────────────────────────────────────────────────────
export default function FraudAlertsView({ flags, loading, showToast, onRefresh }) {
  const [search,        setSearch]        = useState('');
  const [sevFilter,     setSevFilter]     = useState('ALL');
  const [statusFilter,  setStatusFilter]  = useState('OPEN');
  const [resolveTarget, setResolveTarget] = useState(null);
  const [confirming,    setConfirming]    = useState(false);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return [...flags]
      .filter(f => {
        const okSearch = !q || f.rule_triggered?.toLowerCase().includes(q) || f.client_id?.toLowerCase().includes(q) || f.description?.toLowerCase().includes(q);
        const okSev    = sevFilter === 'ALL' || f.severity === sevFilter;
        const okStatus = statusFilter === 'ALL' || f.status === statusFilter;
        return okSearch && okSev && okStatus;
      })
      .sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9));
  }, [flags, search, sevFilter, statusFilter]);

  const stats = {
    total:    flags.length,
    open:     flags.filter(f => f.status === 'OPEN').length,
    critical: flags.filter(f => f.severity === 'CRITICAL').length,
    resolved: flags.filter(f => f.status !== 'OPEN').length,
  };

  const handleConfirmResolve = async (note) => {
    setConfirming(true);
    try {
      await api.resolveFlag(resolveTarget.id, note);
      showToast(`Flag ${resolveTarget.id.slice(0, 8)}… resolved`, 'success');
      setResolveTarget(null);
      onRefresh();
    } catch (e) {
      showToast(`Failed: ${e.message}`, 'error');
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Page title */}
      <div>
        <h2 className="text-xl font-extrabold text-gray-900">Fraud Alert Management</h2>
        <p className="text-sm text-gray-400 mt-0.5">
          AML / Fraud detection flags — review, investigate, and resolve with full audit trail
        </p>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Total Flags', value: stats.total,    color: '#1e293b'  },
          { label: 'Open',        value: stats.open,     color: '#ea580c'  },
          { label: 'Critical',    value: stats.critical, color: '#dc2626'  },
          { label: 'Resolved',    value: stats.resolved, color: '#16a34a'  },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 text-center">
            <p className="text-2xl font-extrabold" style={{ color: s.color }}>{s.value}</p>
            <p className="text-xs text-gray-400 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Filters bar */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-5 py-3.5 flex items-center gap-3 flex-wrap">
        {/* Search */}
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search rule, client, description…"
            className="pl-8 pr-4 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-200 w-full"
          />
        </div>

        {/* Severity pills */}
        {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(s => (
          <button
            key={s}
            onClick={() => setSevFilter(s)}
            className={clsx('px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors', sevFilter === s ? 'text-white border-transparent' : 'text-gray-600 border-gray-200 hover:bg-gray-50')}
            style={sevFilter === s ? { background: '#1e293b' } : {}}
          >
            {s === 'ALL' ? 'All Severities' : s}
          </button>
        ))}

        <div className="h-5 border-l border-gray-200 mx-1" />

        {/* Status pills */}
        {[['OPEN', 'Open Only'], ['ALL', 'All Status']].map(([val, lbl]) => (
          <button
            key={val}
            onClick={() => setStatusFilter(val)}
            className={clsx('px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors', statusFilter === val ? 'text-white border-transparent' : 'text-gray-600 border-gray-200 hover:bg-gray-50')}
            style={statusFilter === val ? { background: '#1e293b' } : {}}
          >
            {lbl}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <th className="px-5 py-3 text-left">Severity</th>
                <th className="px-4 py-3 text-left">Rule</th>
                <th className="px-4 py-3 text-left">Client</th>
                <th className="px-4 py-3 text-left">Description</th>
                <th className="px-4 py-3 text-left">Amount</th>
                <th className="px-4 py-3 text-left">Detected</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {loading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i} className="animate-pulse">
                      {Array.from({ length: 8 }).map((_, j) => (
                        <td key={j} className="px-4 py-4">
                          <div className="h-4 bg-gray-100 rounded" />
                        </td>
                      ))}
                    </tr>
                  ))
                : !filtered.length
                ? (
                  <tr>
                    <td colSpan={8} className="text-center py-14 text-sm text-gray-400">
                      No matching alerts
                    </td>
                  </tr>
                )
                : filtered.map(flag => (
                  <tr key={flag.id} className="hover:bg-[#faf8fc] transition-colors">
                    <td className="px-5 py-3.5">
                      <span className={clsx('text-xs font-bold px-2.5 py-1 rounded-full border', SEV_STYLE[flag.severity] ?? 'bg-gray-100 text-gray-600')}>
                        {flag.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="text-xs font-mono font-bold text-[#1e293b]">{flag.rule_triggered}</span>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="text-xs font-mono text-gray-700">{flag.client_id?.slice(0, 14)}…</span>
                    </td>
                    <td className="px-4 py-3.5 max-w-xs">
                      <p className="text-xs text-gray-600 truncate">{flag.description}</p>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="text-xs font-semibold text-gray-800 tabular-nums">
                        {flag.flagged_amount != null ? fmtOMRFull(flag.flagged_amount) : '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-1.5 text-xs text-gray-400">
                        <Clock className="w-3 h-3" />
                        {ago(flag.flagged_at)}
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={clsx(
                        'text-xs font-semibold px-2 py-0.5 rounded-full',
                        flag.status === 'OPEN' ? 'bg-orange-50 text-orange-700' : 'bg-green-50 text-green-700',
                      )}>
                        {flag.status}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      {flag.status === 'OPEN' ? (
                        <button
                          onClick={() => setResolveTarget(flag)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg text-white transition-all active:scale-95"
                          style={{ background: '#16a34a' }}
                        >
                          <CheckCircle className="w-3 h-3" />
                          Resolve
                        </button>
                      ) : (
                        <span className="text-xs text-green-600 font-medium">Closed</span>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Resolve modal */}
      {resolveTarget && (
        <ResolveModal
          flag={resolveTarget}
          onClose={() => setResolveTarget(null)}
          onConfirm={handleConfirmResolve}
          confirming={confirming}
        />
      )}
    </div>
  );
}
