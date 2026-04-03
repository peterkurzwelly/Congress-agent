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
  const [statsLoading, setStatsLoading] = useState(true);
  const [topTraders, setTopTraders] = useState<Member[]>([]);
  const [tradersLoading, setTradersLoading] = useState(true);
  const [sectorFlows, setSectorFlows] = useState<SectorFlow[]>([]);
  const [sectorsLoading, setSectorsLoading] = useState(true);
  const [anomalies, setAnomalies] = useState<Trade[]>([]);
  const [anomaliesLoading, setAnomaliesLoading] = useState(true);
  const [expandedAnomaly, setExpandedAnomaly] = useState<string | null>(null);
  const [lateFilers, setLateFilers] = useState<Member[]>([]);
  const [lateFilerLoading, setLateFilerLoading] = useState(true);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(true);

  useEffect(() => {
    api.getStats().then(setStats).catch(console.error).finally(() => setStatsLoading(false));
    api.getTopTraders(10).then(setTopTraders).catch(console.error).finally(() => setTradersLoading(false));
    api.getSectorFlows().then(setSectorFlows).catch(console.error).finally(() => setSectorsLoading(false));
    api.getAnomalies(50).then((data) => setAnomalies(Array.isArray(data) ? data.slice(0, 10) : [])).catch(console.error).finally(() => setAnomaliesLoading(false));
    api.getLateFilers().then(setLateFilers).catch(console.error).finally(() => setLateFilerLoading(false));
    api.getTimeline().then(setTimeline).catch(console.error).finally(() => setTimelineLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>

      {/* Stats Cards */}
      {statsLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="bg-slate-800 border border-slate-700 rounded-lg p-4 animate-pulse">
              <div className="h-3 bg-slate-700 rounded w-20 mb-2" />
              <div className="h-7 bg-slate-700 rounded w-16" />
            </div>
          ))}
        </div>
      ) : stats ? (
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
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Trade Timeline Chart */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">Trade Volume Over Time</h2>
          {timelineLoading ? (
            <div className="h-[250px] flex items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
            </div>
          ) : timeline.length > 0 ? (
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
            <div className="h-[250px] flex items-center justify-center text-slate-500">No data available</div>
          )}
        </div>

        {/* Top Traders Leaderboard */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">Top Traders</h2>
          <div className="space-y-2">
            {tradersLoading ? (
              <div className="animate-pulse space-y-2">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-10 bg-slate-700 rounded" />
                ))}
              </div>
            ) : topTraders.length > 0 ? (
              topTraders.map((member, idx) => (
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
              ))
            ) : (
              <div className="text-slate-500 text-center py-4">No traders found</div>
            )}
          </div>
        </div>
      </div>

      {/* Sector Heatmap */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
        <h2 className="text-lg font-semibold text-slate-100 mb-4">Sector Flows (Net Buy/Sell)</h2>
        {sectorsLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
          </div>
        ) : sectorFlows.length > 0 ? (
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
          <div className="text-slate-500 text-center py-4">No sector data available</div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Anomalies */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">Recent Anomalies</h2>
          <div className="space-y-2">
            {anomaliesLoading ? (
              <div className="animate-pulse space-y-2">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-10 bg-slate-700 rounded" />
                ))}
              </div>
            ) : anomalies.length > 0 ? (
              anomalies.map((trade, idx) => {
                const key = trade.id ?? String(idx);
                const isExpanded = expandedAnomaly === key;
                return (
                  <div key={key}>
                    <button
                      onClick={() => setExpandedAnomaly(isExpanded ? null : key)}
                      className="w-full flex items-center justify-between p-2 rounded hover:bg-slate-700/30 text-sm text-left"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <AnomalyBadge score={trade.anomaly_score} />
                        {trade.bioguide_id ? (
                          <Link
                            to={`/members/${trade.bioguide_id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-blue-400 hover:text-blue-300 hover:underline truncate"
                          >
                            {trade.politician}
                          </Link>
                        ) : (
                          <span className="text-slate-300 truncate">{trade.politician}</span>
                        )}
                        <TradeTypeBadge type={trade.trade_type} />
                        <span className="font-mono text-slate-200">{trade.ticker}</span>
                      </div>
                      <div className="flex items-center gap-2 ml-2">
                        <span className="text-slate-500 text-xs whitespace-nowrap">{trade.transaction_date}</span>
                        <span className="text-slate-500 text-xs">{isExpanded ? '\u25B2' : '\u25BC'}</span>
                      </div>
                    </button>
                    {isExpanded && (
                      <div className="ml-8 mt-1 mb-2 p-3 bg-slate-900/50 rounded border border-slate-700 text-xs space-y-1">
                        {trade.asset_name && (
                          <div><span className="text-slate-500">Asset:</span> <span className="text-slate-300">{trade.asset_name}</span></div>
                        )}
                        <div><span className="text-slate-500">Amount:</span> <span className="text-slate-300">{trade.amount_range}</span></div>
                        {trade.sector && (
                          <div><span className="text-slate-500">Sector:</span> <span className="text-slate-300">{trade.sector}</span></div>
                        )}
                        {trade.anomaly_reasons && trade.anomaly_reasons.length > 0 && (
                          <div>
                            <span className="text-slate-500">Flags:</span>
                            <ul className="mt-1 space-y-0.5">
                              {trade.anomaly_reasons.map((reason, i) => (
                                <li key={i} className="text-amber-400 flex items-center gap-1">
                                  <span className="text-amber-500">&#9679;</span> {reason}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="text-slate-500 text-center py-4">No anomalies found</div>
            )}
          </div>
        </div>

        {/* Late Filing Alerts */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">Late Filing Alerts (STOCK Act)</h2>
          <div className="space-y-2">
            {lateFilerLoading ? (
              <div className="animate-pulse space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 bg-slate-700 rounded" />
                ))}
              </div>
            ) : null}
            {!lateFilerLoading && lateFilers.map((member) => (
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
            {!lateFilerLoading && lateFilers.length === 0 && (
              <div className="text-slate-500 text-center py-4">No late filings found</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
