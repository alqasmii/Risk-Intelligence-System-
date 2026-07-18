import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, LabelList,
} from 'recharts';

const TIER_ORDER  = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
const TIER_COLORS = { LOW: '#16a34a', MEDIUM: '#d97706', HIGH: '#ea580c', CRITICAL: '#dc2626' };
const RETAIL_CLR  = '#1e293b';
const CORP_CLR    = '#3b82f6';

function transformData(raw) {
  if (!raw?.length) return [];
  const map = {};
  for (const item of raw) {
    if (!map[item.risk_tier]) map[item.risk_tier] = { tier: item.risk_tier, RETAIL: 0, CORPORATE: 0 };
    if (item.client_type === 'RETAIL')    map[item.risk_tier].RETAIL    = item.count;
    if (item.client_type === 'CORPORATE') map[item.risk_tier].CORPORATE = item.count;
  }
  return TIER_ORDER.filter(t => map[t]).map(t => map[t]);
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-lg p-3 text-xs">
      <p className="font-bold text-gray-800 mb-2">{label} Risk Tier</p>
      {payload.map(p => (
        <div key={p.name} className="flex items-center justify-between gap-6 mb-0.5">
          <span className="flex items-center gap-1.5 text-gray-600">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ background: p.fill }} />
            {p.name}
          </span>
          <span className="font-bold text-gray-900">{p.value} clients</span>
        </div>
      ))}
    </div>
  );
};

export default function RiskDistributionChart({ data, loading }) {
  const chartData = transformData(data);

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6" style={{ height: 340 }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-sm font-bold text-gray-900">Risk Tier Distribution</h3>
          <p className="text-xs text-gray-400 mt-0.5">Client count by tier and segment</p>
        </div>
        <div className="flex items-center gap-5 text-xs text-gray-500">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm" style={{ background: RETAIL_CLR }} /> Retail
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm" style={{ background: CORP_CLR }} /> Corporate
          </span>
        </div>
      </div>

      {/* Chart body */}
      {loading ? (
        <div className="flex items-end gap-6 h-48 px-4 animate-pulse">
          {[55, 75, 45, 25].map((h, i) => (
            <div key={i} className="flex-1 flex gap-1 items-end">
              <div className="flex-1 bg-gray-200 rounded-t" style={{ height: `${h}%` }} />
              <div className="flex-1 bg-gray-100 rounded-t" style={{ height: `${h * 0.55}%` }} />
            </div>
          ))}
        </div>
      ) : !chartData.length ? (
        <div className="flex items-center justify-center h-48 text-sm text-gray-400">
          No data — click <span className="font-semibold mx-1 text-[#1e293b]">Run Pipeline</span> first
        </div>
      ) : (
        <ResponsiveContainer width="100%" height="85%">
          <BarChart data={chartData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }} barCategoryGap="35%">
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis
              dataKey="tier"
              tick={{ fontSize: 11, fill: '#6b7280', fontWeight: 600 }}
              axisLine={false} tickLine={false}
            />
            <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(30,41,59,0.03)' }} />
            <Bar dataKey="RETAIL" fill={RETAIL_CLR} radius={[4, 4, 0, 0]} maxBarSize={44}>
              <LabelList dataKey="RETAIL" position="top" style={{ fontSize: 10, fill: '#6b7280', fontWeight: 600 }} />
            </Bar>
            <Bar dataKey="CORPORATE" fill={CORP_CLR} radius={[4, 4, 0, 0]} maxBarSize={44}>
              <LabelList dataKey="CORPORATE" position="top" style={{ fontSize: 10, fill: '#6b7280', fontWeight: 600 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
