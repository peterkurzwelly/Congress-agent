import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { api, type Stats, type Member, type Trade, type SectorFlow, type TimelinePoint } from '../api/client';
import PartyBadge from '../components/PartyBadge';
import AnomalyBadge from '../components/AnomalyBadge';
import TradeTypeBadge from '../components/TradeTypeBadge';

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [topTraders, setTopTraders] = useState<Member[]>([]);
  const [sectorFlows, setSectorFlows] = useState<SectorFlow[]>([]);
  const [anomalies, setAnomalies] = useState<Trade[]>([]);
  const [lateFilers, setLateFilers] = useState<Member[]>([]);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);

  useEffect(() => {
    api.getStats().then(setStats).catch(console.error);
    api.getTopTraders(10).then(setTopTraders).catch(console.error);
    api.getSectorFlows().then(setSectorFlows).catch(console.error);
    api.getAnomalies(50).then((data) => setAnomalies(Array.isArray(data) ? data.slice(0, 10) : [])).catch(console.error);
    api.getLateFilers().then(setLateFilers).catch(console.error);
    api.getTimeline().then(setTimeline).catch(console.error);
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[
            { label: 'Total Trades', value: stats.total_trades, color: 'text-slate-100' },
            { label: 'Buys', value: stats.total_buys, color: 'text-green-400' },
            { label: 'Sells', value: stats.total_sells, color: 'text-red-400' },
            { label: 'Unique Tickers', value: stats.unique_tickers, color: 'text-blue-400' },
            { label: 'Members Trading', value: stats.unique_members, color: 'text-purple-400' },
          ].map((s) => (
            <div key={s.label} className="bg-slate-800 border border-slate-700 rounded-lg p-4">
              <div className="text-slate-400 text-xs uppercase tracking-wide mb-1">{s.label}</div>
              <div className={`text-2xl font-bold ${s.color}`}>{s.value?.toLocaleString() ?? '--'}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Trade Timeline Chart */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">Trade Volume Over Time</h2>
          {timeline.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={timeline}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }}
                />
                <Bar dataKey="count" fill="#3b82f6" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-slate-500">Loading...</div>
          )}
        </div>

        {/* Top Traders Leaderboard */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">Top Traders</h2>
          <div className="space-y-2">
            {topTraders.map((member, idx) => (
              <Link
                key={member.bioguide_id}
                to={`/members/${member.bioguide_id}`}
                className="flex items-center justify-between p-2 rounded hover:bg-slate-700/50 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <span className="text-slate-500 text-sm font-mono w-5">{idx + 1}</span>
                  <span className="text-slate-200 group-hover:text-blue-400 transition-colors">{member.name}</span>
                  <PartyBadge party={member.party} />
                </div>
                <span className="text-slate-400 text-sm font-mono">
                  {member.trade_count} trades
                </span>
              </Link>
            ))}
            {topTraders.length === 0 && (
              <div className="text-slate-500 text-center py-4">Loading...</div>
            )}
          </div>
        </div>
      </div>

      {/* Sector Heatmap */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
        <h2 className="text-lg font-semibold text-slate-100 mb-4">Sector Flows (Net Buy/Sell)</h2>
        {sectorFlows.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
            {sectorFlows.map((sector) => {
              const isPositive = sector.net_flow >= 0;
              const intensity = Math.min(Math.abs(sector.net_flow) / (Math.max(...sectorFlows.map(s => Math.abs(s.net_flow))) || 1), 1);
              const bg = isPositive
                ? `rgba(34, 197, 94, ${0.1 + intensity * 0.4})`
                : `rgba(239, 68, 68, ${0.1 + intensity * 0.4})`;
              return (
                <div
                  key={sector.sector}
                  className="rounded-lg p-3 border border-slate-700"
                  style={{ backgroundColor: bg }}
                >
                  <div className="text-xs text-slate-300 truncate" title={sector.sector}>
                    {sector.sector}
                  </div>
                  <div className={`text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                    {isPositive ? '+' : ''}{sector.net_flow}
                  </div>
                  <div className="text-xs text-slate-500">{sector.trade_count} trades</div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-slate-500 text-center py-4">Loading...</div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Anomalies */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">Recent Anomalies</h2>
          <div className="space-y-2">
            {anomalies.map((trade, idx) => (
              <div key={trade.id ?? idx} className="flex items-center justify-between p-2 rounded hover:bg-slate-700/30 text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <AnomalyBadge score={trade.anomaly_score} />
                  <span className="text-slate-300 truncate">{trade.politician}</span>
                  <TradeTypeBadge type={trade.trade_type} />
                  <span className="font-mono text-slate-200">{trade.ticker}</span>
                </div>
                <span className="text-slate-500 text-xs whitespace-nowrap ml-2">{trade.transaction_date}</span>
              </div>
            ))}
            {anomalies.length === 0 && (
              <div className="text-slate-500 text-center py-4">Loading...</div>
            )}
          </div>
        </div>

        {/* Late Filing Alerts */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">Late Filing Alerts (STOCK Act)</h2>
          <div className="space-y-2">
            {lateFilers.map((member) => (
              <Link
                key={member.bioguide_id}
                to={`/members/${member.bioguide_id}`}
                className="flex items-center justify-between p-2 rounded hover:bg-slate-700/50 transition-colors group"
              >
                <div className="flex items-center gap-2">
                  <span className="text-amber-400 text-sm">&#9888;</span>
                  <span className="text-slate-200 group-hover:text-blue-400 transition-colors">{member.name}</span>
                  <PartyBadge party={member.party} />
                </div>
                <span className="text-slate-500 text-xs">{member.state} - {member.chamber}</span>
              </Link>
            ))}
            {lateFilers.length === 0 && (
              <div className="text-slate-500 text-center py-4">No late filings found</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
