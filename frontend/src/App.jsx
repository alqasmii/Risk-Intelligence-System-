import { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar.jsx';
import Header from './components/Header.jsx';
import KPICards from './components/KPICards.jsx';
import RiskDistributionChart from './components/RiskDistributionChart.jsx';
import ClientTable from './components/ClientTable.jsx';
import AlertsPanel from './components/AlertsPanel.jsx';
import FraudAlertsView from './components/FraudAlertsView.jsx';
import LiveAIRiskFeed from './components/LiveAIRiskFeed.jsx';
import LiveTransactionsView from './components/LiveTransactionsView.jsx';
import StressTestView from './components/StressTestView.jsx';
import SettingsView from './components/SettingsView.jsx';
import PortfolioAnalyticsView from './components/PortfolioAnalyticsView.jsx';
import ClientExplorerView from './components/ClientExplorerView.jsx';
import { api } from './services/api.js';

// ── Toast ────────────────────────────────────────────────────────────────────
function Toast({ toast }) {
  if (!toast) return null;
  const bg = toast.type === 'success' ? '#16a34a'
           : toast.type === 'error'   ? '#dc2626'
           :                            '#1e293b';
  return (
    <div
      className="fixed bottom-6 right-6 z-50 px-5 py-3 rounded-xl shadow-xl text-white text-sm font-medium"
      style={{ background: bg, maxWidth: 380 }}
    >
      {toast.msg}
    </div>
  );
}

// ── Root ─────────────────────────────────────────────────────────────────────
export default function App() {
  const [activePage,      setActivePage]      = useState('dashboard');
  const [heatmapData,     setHeatmapData]     = useState(null);
  const [anomalyFlags,    setAnomalyFlags]    = useState([]);
  const [apiStatus,       setApiStatus]       = useState('checking');
  const [loading,         setLoading]         = useState(true);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [toast,           setToast]           = useState(null);

  const showToast = useCallback((msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      await api.health();
      setApiStatus('online');
      const [heatmap, flags] = await Promise.all([
        api.getRiskHeatmap(),
        api.getAnomalyFlags({ limit: 200 }),
      ]);
      setHeatmapData(heatmap);
      setAnomalyFlags(Array.isArray(flags) ? flags : []);
    } catch {
      setApiStatus('offline');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Auto-recover: if the API is offline, retry every 8 seconds until it comes back
  useEffect(() => {
    if (apiStatus !== 'offline') return;
    const t = setInterval(() => { fetchData(); }, 8000);
    return () => clearInterval(t);
  }, [apiStatus, fetchData]);

  const runPipeline = async () => {
    setPipelineRunning(true);
    try {
      await api.ingest();
      showToast('Data ingested ✓', 'info');
      await api.scorePortfolio();
      showToast('Portfolio scored ✓', 'info');
      const result = await api.scanAnomalies();
      showToast(
        `Pipeline complete — ${result.anomalies_detected ?? '?'} anomalies detected`,
        'success',
      );
      await fetchData();
    } catch (e) {
      showToast(`Pipeline error: ${e.message}`, 'error');
    } finally {
      setPipelineRunning(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#f1f5f9] overflow-hidden font-sans">
      <Sidebar activePage={activePage} setActivePage={setActivePage} />

      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Header
          apiStatus={apiStatus}
          onRefresh={fetchData}
          onRunPipeline={runPipeline}
          pipelineRunning={pipelineRunning}
          loading={loading}
        />

        <main className="flex-1 overflow-y-auto p-6">
          {activePage === 'dashboard' && (
            <div className="space-y-6">
              <KPICards
                data={heatmapData?.summary}
                totalClients={heatmapData?.total_clients_analyzed}
                loading={loading}
                apiStatus={apiStatus}
              />
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div className="xl:col-span-2">
                  <RiskDistributionChart
                    data={heatmapData?.tier_distribution}
                    loading={loading}
                  />
                </div>
                <AlertsPanel flags={anomalyFlags} loading={loading} />
              </div>

              {/* ── Adverse Media Early Warning Radar ─────────────────────── */}
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 items-start">
                <div className="xl:col-span-2">
                  <ClientTable
                    clients={heatmapData?.high_risk_clients}
                    loading={loading}
                    showToast={showToast}
                    onRefresh={fetchData}
                  />
                </div>
                <LiveAIRiskFeed />
              </div>
            </div>
          )}

          {activePage === 'fraud-alerts' && (
            <FraudAlertsView
              flags={anomalyFlags}
              loading={loading}
              showToast={showToast}
              onRefresh={fetchData}
            />
          )}

          {activePage === 'clients'      && <ClientExplorerView />}
          {activePage === 'transactions' && <LiveTransactionsView />}
          {activePage === 'analytics'    && <PortfolioAnalyticsView />}
          {activePage === 'stress-tests' && <StressTestView showToast={showToast} />}
          {activePage === 'settings'     && <SettingsView showToast={showToast} />}
        </main>
      </div>

      <Toast toast={toast} />
    </div>
  );
}
