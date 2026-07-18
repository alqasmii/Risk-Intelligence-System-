import { useState, useEffect } from 'react';
import { RefreshCw, PlayCircle, Clock, Wifi, WifiOff, Loader2 } from 'lucide-react';
import clsx from 'clsx';

const STATUS = {
  online:   { dot: 'bg-green-500 animate-pulse', text: 'text-green-700', bg: 'bg-green-50 border-green-200', label: 'API Connected' },
  offline:  { dot: 'bg-red-500',                 text: 'text-red-700',   bg: 'bg-red-50 border-red-200',     label: 'API Offline'   },
  checking: { dot: 'bg-amber-400 animate-pulse',  text: 'text-amber-700', bg: 'bg-amber-50 border-amber-200', label: 'Connecting…'  },
};

export default function Header({ apiStatus, onRefresh, onRunPipeline, pipelineRunning, loading }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const s = STATUS[apiStatus] ?? STATUS.checking;

  return (
    <header className="bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between flex-shrink-0 shadow-sm">
      {/* Left */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-extrabold tracking-tight text-gray-900">
            Risk Intelligence Dashboard
          </h1>
          {/* Live Demo badge */}
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 border border-emerald-200 text-emerald-700 select-none">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Live Demo
          </span>
        </div>
        <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1.5">
          <Clock className="w-3 h-3" />
          {now.toLocaleDateString(undefined, {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
          })}
          &nbsp;·&nbsp;
          {now.toLocaleTimeString(undefined)}
        </p>
      </div>

      {/* Right */}
      <div className="flex items-center gap-3">
        {/* Status badge */}
        <div className={clsx('flex items-center gap-2 border rounded-full px-3 py-1.5 text-xs font-semibold', s.bg, s.text)}>
          <span className={clsx('w-2 h-2 rounded-full', s.dot)} />
          {s.label}
        </div>

        {/* Refresh */}
        <button
          onClick={onRefresh}
          disabled={loading}
          title="Refresh data"
          className="p-2 rounded-lg text-gray-400 hover:text-[#1e293b] hover:bg-blue-50 transition-colors disabled:opacity-40"
        >
          <RefreshCw className={clsx('w-4 h-4', loading && 'animate-spin')} />
        </button>

        {/* Run pipeline */}
        <button
          onClick={onRunPipeline}
          disabled={pipelineRunning || loading}
          className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg text-white transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ background: '#1e293b' }}
        >
          {pipelineRunning
            ? <Loader2 className="w-4 h-4 animate-spin" />
            : <PlayCircle className="w-4 h-4" />
          }
          {pipelineRunning ? 'Running…' : 'Run Pipeline'}
        </button>
      </div>
    </header>
  );
}
