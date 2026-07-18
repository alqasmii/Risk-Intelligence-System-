import { TrendingUp, AlertTriangle, Wifi, WifiOff } from 'lucide-react';
import { fmtOMR } from '../utils/format.js';

function Skeleton() {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 animate-pulse">
      <div className="flex items-start justify-between mb-4">
        <div className="space-y-2">
          <div className="h-3 w-36 bg-gray-200 rounded" />
          <div className="h-9 w-28 bg-gray-200 rounded" />
        </div>
        <div className="w-11 h-11 bg-gray-100 rounded-xl" />
      </div>
      <div className="h-3 w-24 bg-gray-100 rounded" />
    </div>
  );
}

function KPICard({ title, value, sub, leftColor, icon: Icon, iconBg, iconColor, badge }) {
  return (
    <div
      className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 border-l-4"
      style={{ borderLeftColor: leftColor }}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">{title}</p>
          <p className="text-3xl font-extrabold text-gray-900 mt-1 tracking-tight">{value}</p>
        </div>
        <div
          className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: iconBg }}
        >
          <Icon className="w-5 h-5" style={{ color: iconColor }} />
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">{sub}</div>
    </div>
  );
}

export default function KPICards({ data, totalClients, loading, apiStatus }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <Skeleton /><Skeleton /><Skeleton />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
      {/* ── Exposure ──────────────────────────────────────────────────────── */}
      <KPICard
        title="Total Active Exposure"
        value={data ? fmtOMR(data.total_exposure_usd) : '—'}
        leftColor="#1e293b"
        icon={TrendingUp}
        iconBg="rgba(30,41,59,0.08)"
        iconColor="#1e293b"
        sub={
          <>
            <span className="text-xs font-medium bg-green-50 text-green-700 px-2 py-0.5 rounded-full">
              +4.2% MTD
            </span>
            <span className="text-xs text-gray-400">
              {totalClients ?? '—'} clients analyzed
            </span>
          </>
        }
      />

      {/* ── High-risk accounts ────────────────────────────────────────────── */}
      <KPICard
        title="High-Risk Accounts Flagged"
        value={data?.total_high_risk ?? '—'}
        leftColor="#3b82f6"
        icon={AlertTriangle}
        iconBg="rgba(59,130,246,0.12)"
        iconColor="#3b82f6"
        sub={
          <>
            <span className="text-xs font-bold bg-red-50 text-red-700 border border-red-200 px-2 py-0.5 rounded-full">
              {data?.total_critical ?? '—'} CRITICAL
            </span>
            <span className="text-xs text-gray-400">
              {data?.total_open_anomalies ?? '—'} open flags
            </span>
          </>
        }
      />

      {/* ── System status ─────────────────────────────────────────────────── */}
      <KPICard
        title="System Status"
        value={
          <span style={{ color: apiStatus === 'online' ? '#16a34a' : '#dc2626' }}>
            {apiStatus === 'online' ? 'LIVE' : apiStatus === 'offline' ? 'DOWN' : '…'}
          </span>
        }
        leftColor={apiStatus === 'online' ? '#16a34a' : '#dc2626'}
        icon={apiStatus === 'online' ? Wifi : WifiOff}
        iconBg={apiStatus === 'online' ? 'rgba(22,163,74,0.08)' : 'rgba(220,38,38,0.08)'}
        iconColor={apiStatus === 'online' ? '#16a34a' : '#dc2626'}
        sub={
          <>
            <span
              className="flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full"
              style={
                apiStatus === 'online'
                  ? { background: '#f0fdf4', color: '#15803d' }
                  : { background: '#fef2f2', color: '#dc2626' }
              }
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${apiStatus === 'online' ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}
              />
              {apiStatus === 'online' ? 'API Connected' : apiStatus === 'offline' ? 'API Offline' : 'Connecting…'}
            </span>
            <span className="text-xs text-gray-400">FastAPI v0.104</span>
          </>
        }
      />
    </div>
  );
}
