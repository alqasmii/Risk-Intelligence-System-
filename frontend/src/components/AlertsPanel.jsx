import { AlertTriangle, Clock } from 'lucide-react';
import clsx from 'clsx';

const SEV = {
  CRITICAL: { bg: 'bg-red-50',    border: 'border-red-200',    dot: 'bg-red-500',    badge: 'bg-red-100 text-red-700'    },
  HIGH:     { bg: 'bg-orange-50', border: 'border-orange-200', dot: 'bg-orange-500', badge: 'bg-orange-100 text-orange-700' },
  MEDIUM:   { bg: 'bg-amber-50',  border: 'border-amber-200',  dot: 'bg-amber-400',  badge: 'bg-amber-100 text-amber-700'  },
  LOW:      { bg: 'bg-sky-50',    border: 'border-sky-200',    dot: 'bg-sky-400',    badge: 'bg-sky-100 text-sky-700'      },
};

function ago(dateStr) {
  const d = (Date.now() - new Date(dateStr)) / 1000;
  if (d < 60)    return `${Math.floor(d)}s ago`;
  if (d < 3600)  return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

export default function AlertsPanel({ flags, loading }) {
  const open  = flags.filter(f => f.status === 'OPEN');
  const sorted = [...open]
    .sort((a, b) => ({ CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }[a.severity] ?? 4) - ({ CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }[b.severity] ?? 4))
    .slice(0, 7);

  const critCount = open.filter(f => f.severity === 'CRITICAL').length;

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex flex-col" style={{ height: 340 }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div>
          <h3 className="text-sm font-bold text-gray-900">Live Alert Queue</h3>
          <p className="text-xs text-gray-400 mt-0.5">{open.length} open flags</p>
        </div>
        {critCount > 0 && (
          <span
            className="flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full"
            style={{ background: 'rgba(220,38,38,0.09)', color: '#dc2626' }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            {critCount} Critical
          </span>
        )}
      </div>

      {/* Scroll list */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-0.5">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-[60px] bg-gray-100 rounded-xl animate-pulse" />
          ))
        ) : !sorted.length ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 text-sm gap-2">
            <AlertTriangle className="w-8 h-8 opacity-25" />
            No open alerts
          </div>
        ) : (
          sorted.map(flag => {
            const c = SEV[flag.severity] ?? SEV.MEDIUM;
            return (
              <div
                key={flag.id}
                className={clsx('flex items-start gap-2.5 p-2.5 rounded-xl border', c.bg, c.border)}
              >
                <span className={clsx('w-2 h-2 rounded-full mt-[5px] flex-shrink-0', c.dot)} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className={clsx('text-xs font-bold px-1.5 py-0.5 rounded', c.badge)}>
                      {flag.severity}
                    </span>
                    <span className="text-xs font-mono font-semibold text-gray-800 truncate">
                      {flag.rule_triggered}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 truncate">{flag.description}</p>
                  <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1">
                    <Clock className="w-3 h-3" /> {ago(flag.flagged_at)}
                  </p>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
