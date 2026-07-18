import { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api.js';

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(iso) {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60)       return `${diff}s ago`;
  if (diff < 3600)     return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400)    return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function ScoreBadge({ score }) {
  let bg, label;
  if (score >= 9)      { bg = '#dc2626'; label = 'CRITICAL'; }
  else if (score >= 7) { bg = '#ea580c'; label = 'HIGH'; }
  else if (score >= 5) { bg = '#d97706'; label = 'MEDIUM'; }
  else                 { bg = '#16a34a'; label = 'LOW'; }

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-white font-bold text-xs tracking-wide select-none"
      style={{ background: bg }}
    >
      <span className="text-[10px]">●</span>
      {score}/10 {label}
    </span>
  );
}

// Skeleton card while loading
function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-xl p-3 border border-white/10" style={{ background: 'rgba(255,255,255,0.04)' }}>
      <div className="flex justify-between mb-2">
        <div className="h-3 rounded w-32 bg-white/20" />
        <div className="h-3 rounded w-16 bg-white/10" />
      </div>
      <div className="h-2 rounded w-full bg-white/10 mb-1.5" />
      <div className="h-2 rounded w-4/5 bg-white/10" />
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function LiveAIRiskFeed({ className = '' }) {
  const [alerts,     setAlerts]     = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState(null);
  const [acking,     setAcking]     = useState(null);   // alert id being acknowledged
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetch = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await api.getAIAlerts({ limit: 20 });
      setAlerts(Array.isArray(data) ? data : []);
      setLastUpdated(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => { fetch(); }, [fetch]);

  // Auto-refresh every 30 s
  useEffect(() => {
    const id = setInterval(() => fetch(true), 30_000);
    return () => clearInterval(id);
  }, [fetch]);

  const handleAcknowledge = async (alert) => {
    setAcking(alert.id);
    try {
      await api.acknowledgeAlert(alert.id, 'Analyst');
      // Optimistically update the local list
      setAlerts(prev =>
        prev.map(a => a.id === alert.id
          ? { ...a, is_acknowledged: true, acknowledged_by: 'Analyst', acknowledged_at: new Date().toISOString() }
          : a
        )
      );
    } catch (e) {
      // silently fail — next poll will reconcile
    } finally {
      setAcking(null);
    }
  };

  const unackedCount = alerts.filter(a => !a.is_acknowledged).length;
  const criticalCount = alerts.filter(a => a.risk_score >= 8 && !a.is_acknowledged).length;

  return (
    <div
      className={`flex flex-col rounded-2xl overflow-hidden shadow-xl ${className}`}
      style={{ background: '#0f172a', border: '1px solid rgba(59,130,246,0.2)' }}
    >
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ background: '#1e293b', borderBottom: '1px solid rgba(59,130,246,0.25)' }}
      >
        <div className="flex items-center gap-2.5">
          {/* Pulsing live indicator */}
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                  style={{ background: criticalCount > 0 ? '#ef4444' : '#3b82f6' }} />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5"
                  style={{ background: criticalCount > 0 ? '#dc2626' : '#3b82f6' }} />
          </span>
          <span className="font-bold text-sm tracking-wide" style={{ color: '#3b82f6' }}>
            Live AI Risk Feed
          </span>
        </div>

        <div className="flex items-center gap-2">
          {unackedCount > 0 && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(59,130,246,0.15)', color: '#3b82f6', border: '1px solid rgba(59,130,246,0.3)' }}>
              {unackedCount} open
            </span>
          )}
          {criticalCount > 0 && (
            <span className="text-xs font-bold px-2 py-0.5 rounded-full animate-pulse"
                  style={{ background: 'rgba(220,38,38,0.25)', color: '#fca5a5', border: '1px solid rgba(220,38,38,0.5)' }}>
              {criticalCount} critical
            </span>
          )}
          <button
            onClick={() => fetch(false)}
            disabled={loading}
            className="text-xs opacity-60 hover:opacity-100 transition-opacity px-1.5"
            style={{ color: '#3b82f6' }}
            title="Refresh"
          >
            {loading ? '⟳' : '↺'}
          </button>
        </div>
      </div>

      {/* ── Sub-header ───────────────────────────────────────────────────────── */}
      <div className="px-4 py-1.5 flex items-center justify-between"
           style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <span className="text-[11px] text-gray-400">
          n8n · OpenAI GPT-4o-mini · Adverse media analysis
        </span>
        {lastUpdated && (
          <span className="text-[11px] text-gray-500">
            Updated {timeAgo(lastUpdated.toISOString())}
          </span>
        )}
      </div>

      {/* ── Alert List ──────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5" style={{ maxHeight: 420 }}>
        {loading && alerts.length === 0 && (
          <>
            <SkeletonCard /><SkeletonCard /><SkeletonCard />
          </>
        )}

        {error && (
          <div className="text-center py-8">
            <p className="text-sm text-red-400/80">Failed to load alerts</p>
            <p className="text-xs text-gray-500 mt-1">{error}</p>
          </div>
        )}

        {!loading && !error && alerts.length === 0 && (
          <div className="text-center py-10 select-none">
            <div className="text-3xl mb-3 opacity-40">📡</div>
            <p className="text-sm font-medium" style={{ color: '#3b82f6', opacity: 0.7 }}>
              No AI alerts yet
            </p>
            <p className="text-xs text-gray-500 mt-1 leading-relaxed px-4">
              Trigger the n8n Adverse Media Radar workflow to start receiving
              AI-generated risk signals.
            </p>
          </div>
        )}

        {alerts.map(alert => {
          const isCritical = alert.risk_score >= 8 && !alert.is_acknowledged;
          const isHigh     = alert.risk_score >= 6 && !alert.is_acknowledged;
          const isAcking   = acking === alert.id;

          return (
            <div
              key={alert.id}
              className={`rounded-xl p-3 transition-all duration-300 ${alert.is_acknowledged ? 'opacity-50' : ''}`}
              style={{
                background: isCritical
                  ? 'rgba(220,38,38,0.10)'
                  : isHigh
                    ? 'rgba(234,88,12,0.08)'
                    : 'rgba(255,255,255,0.05)',
                border: isCritical
                  ? '1px solid rgba(220,38,38,0.50)'
                  : isHigh
                    ? '1px solid rgba(234,88,12,0.30)'
                    : '1px solid rgba(255,255,255,0.08)',
                boxShadow: isCritical
                  ? '0 0 12px 2px rgba(220,38,38,0.20), inset 0 0 0 1px rgba(59,130,246,0.15)'
                  : undefined,
                animation: isCritical ? 'pulseGold 2s ease-in-out infinite' : undefined,
              }}
            >
              {/* Card header: company + score + time */}
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div className="min-w-0">
                  <p
                    className="font-semibold text-sm truncate leading-tight"
                    style={{ color: isCritical ? '#fca5a5' : isHigh ? '#fdba74' : '#3b82f6' }}
                  >
                    {alert.company_name}
                  </p>
                  <p className="text-[11px] text-gray-500 mt-0.5">
                    {timeAgo(alert.created_at)} · {alert.source.replace('_', ' ')}
                  </p>
                </div>
                <ScoreBadge score={alert.risk_score} />
              </div>

              {/* Risk summary */}
              <p className="text-xs leading-relaxed text-gray-300 line-clamp-3">
                {alert.risk_summary}
              </p>

              {/* Footer: source tag + ack button */}
              <div className="flex items-center justify-between mt-2">
                {alert.is_acknowledged ? (
                  <span className="text-[11px] text-gray-500 italic">
                    ✓ Reviewed by {alert.acknowledged_by}
                  </span>
                ) : (
                  <span className="text-[11px] text-gray-600">
                    &nbsp;
                  </span>
                )}
                {!alert.is_acknowledged && (
                  <button
                    onClick={() => handleAcknowledge(alert)}
                    disabled={isAcking}
                    className="text-[11px] font-semibold px-2.5 py-1 rounded-lg transition-all hover:opacity-90 active:scale-95 disabled:opacity-50"
                    style={{
                      background: isCritical
                        ? 'rgba(59,130,246,0.2)'
                        : 'rgba(255,255,255,0.08)',
                      color: '#3b82f6',
                      border: '1px solid rgba(59,130,246,0.3)',
                    }}
                  >
                    {isAcking ? 'Reviewing…' : 'Acknowledge'}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Footer ──────────────────────────────────────────────────────────── */}
      <div className="px-4 py-2 shrink-0 flex items-center justify-between"
           style={{ borderTop: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)' }}>
        <span className="text-[11px] text-gray-600">
          {alerts.length} alert{alerts.length !== 1 ? 's' : ''} · refreshes every 30s
        </span>
        <span className="text-[11px] font-medium" style={{ color: 'rgba(59,130,246,0.5)' }}>
          Powered by n8n + GPT-4o-mini
        </span>
      </div>

      {/* Pulsing animation keyframes injected via a style tag */}
      <style>{`
        @keyframes pulseGold {
          0%, 100% { box-shadow: 0 0 12px 2px rgba(220,38,38,0.20), inset 0 0 0 1px rgba(59,130,246,0.15); }
          50%       { box-shadow: 0 0 22px 6px rgba(220,38,38,0.35), inset 0 0 0 1px rgba(59,130,246,0.35); }
        }
      `}</style>
    </div>
  );
}
