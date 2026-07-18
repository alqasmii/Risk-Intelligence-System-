import clsx from 'clsx';
import {
  LayoutDashboard,
  Activity,
  AlertTriangle,
  FlaskConical,
  Settings,
  ShieldCheck,
  Users,
  PieChart,
  LogOut,
  ChevronRight,
} from 'lucide-react';

const NAV_ITEMS = [
  { id: 'dashboard',     label: 'Dashboard',           icon: LayoutDashboard },
  { id: 'clients',       label: 'Client Explorer',      icon: Users           },
  { id: 'transactions',  label: 'Live Transactions',    icon: Activity        },
  { id: 'fraud-alerts',  label: 'Fraud Alerts',         icon: AlertTriangle   },
  { id: 'analytics',     label: 'Portfolio Analytics',  icon: PieChart        },
  { id: 'stress-tests',  label: 'Model Stress Tests',   icon: FlaskConical    },
  { id: 'settings',      label: 'Settings',             icon: Settings        },
];

export default function Sidebar({ activePage, setActivePage }) {
  return (
    <aside
      className="w-64 flex-shrink-0 flex flex-col h-full select-none"
      style={{ background: '#0f172a' }}
    >
      {/* ── Brand ─────────────────────────────────────────────────────────── */}
      <div
        className="px-5 py-5 flex items-center gap-3 border-b border-white/10"
        style={{ background: '#1e293b' }}
      >
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: '#3b82f6' }}
        >
          <ShieldCheck className="w-5 h-5" style={{ color: '#0f172a' }} />
        </div>
        <div className="leading-tight">
          <p className="text-white font-extrabold text-sm tracking-wide">DEMO BANK</p>
          <p className="text-xs font-semibold" style={{ color: '#3b82f6' }}>
            Risk Intelligence
          </p>
        </div>
      </div>

      {/* ── Nav label ─────────────────────────────────────────────────────── */}
      <div className="px-5 pt-5 pb-1">
        <p
          className="text-xs font-bold uppercase tracking-widest"
          style={{ color: 'rgba(255,255,255,0.25)' }}
        >
          Navigation
        </p>
      </div>

      {/* ── Nav items ─────────────────────────────────────────────────────── */}
      <nav className="flex-1 px-3 space-y-0.5 mt-1">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const active = activePage === id;
          return (
            <button
              key={id}
              onClick={() => setActivePage(id)}
              className={clsx(
                'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group',
                active
                  ? 'text-[#3b82f6]'
                  : 'text-white/55 hover:text-white/85 hover:bg-white/5',
              )}
              style={
                active
                  ? {
                      background: 'rgba(59,130,246,0.11)',
                      borderLeft: '2px solid #3b82f6',
                      paddingLeft: '10px',
                    }
                  : {}
              }
            >
              <Icon
                className={clsx(
                  'w-4 h-4 flex-shrink-0 transition-colors',
                  active ? 'text-[#3b82f6]' : 'text-white/35 group-hover:text-white/60',
                )}
              />
              <span className="flex-1 text-left">{label}</span>
              {active && <ChevronRight className="w-3.5 h-3.5 text-[#3b82f6]" />}
            </button>
          );
        })}
      </nav>

      {/* ── Divider ───────────────────────────────────────────────────────── */}
      <div className="border-t border-white/10 mx-4 mb-3" />

      {/* ── User ──────────────────────────────────────────────────────────── */}
      <div className="px-4 pb-4">
        <div className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
            style={{ background: '#3b82f6', color: '#0f172a' }}
          >
            RO
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white text-xs font-semibold truncate">Risk Officer</p>
            <p className="text-xs truncate" style={{ color: 'rgba(255,255,255,0.35)' }}>
              risk@demobank.example
            </p>
          </div>
          <LogOut className="w-3.5 h-3.5" style={{ color: 'rgba(255,255,255,0.25)' }} />
        </div>
      </div>
    </aside>
  );
}
