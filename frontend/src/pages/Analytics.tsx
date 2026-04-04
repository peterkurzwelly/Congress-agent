import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend, Cell,
} from 'recharts';
import {
  api,
  type PartyComparison,
  type TopTicker,
  type DisclosureDelayBucket,
  type MemberPerformance,
} from '../api/client';
import PartyBadge from '../components/PartyBadge';
import AnomalyBadge from '../components/AnomalyBadge';

const PARTY_COLORS: Record<string, string> = {
  D: '#3b82f6',
  R: '#ef4444',
  I: '#a855f7',
};

const TOOLTIP_STYLE = {
  contentStyle: {
    backgroundColor: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '8px',
    color: '#f1f5f9',
  },
};

function SectionCard({ title, children, loading }: { title: string; children: React.ReactNode; loading?: boolean }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
      <h2 className="text-lg font-semibold text-slate-100 mb-4">{title}</h2>
      {loading ? (
        <div className="flex items-center justify-center h-[260px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400" />
        </div>
      ) : (
        children
      )}
    </div>
  );
}

function ErrorMsg({ msg }: { msg: string }) {
  return <div className="text-red-400 text-sm text-center py-8">{msg}</div>;
}

export default function Analytics() {
  const [partyData, setPartyData] = useState<PartyComparison[]>([]);
  const [partyLoading, setPartyLoading] = useState(true);
  const [partyError, setPartyError] = useState<string | null>(null);

  const [topTickers, setTopTickers] = useState<TopTicker[]>([]);
  const [tickersLoading, setTickersLoading] = useState(true);
  const [tickersError, setTickersError] = useState<string | null>(null);

  const [delays, setDelays] = useState<DisclosureDelayBucket[]>([]);
  const [delaysLoading, setDelaysLoading] = useState(true);
  const [delaysError, setDelaysError] = useState<string | null>(null);

  const [members, setMembers] = useState<MemberPerformance[]>([]);
  const [membersLoading, setMembersLoading] = useState(true);
  const [membersError, setMembersError] = useState<string | null>(null);

  useEffect(() => {
    api.getPartyComparison()
      .then(setPartyData)
      .catch((e) => setPartyError(e.message ?? 'Failed to load'))
      .finally(() => setPartyLoading(false));

    api.getTopTickers(20)
      .then(setTopTickers)
      .catch((e) => setTickersError(e.message ?? 'Failed to load'))
      .finally(() => setTickersLoading(false));

    api.getDisclosureDelays()
      .then(setDelays)
      .catch((e) => setDelaysError(e.message ?? 'Failed to load'))
      .finally(() => setDelaysLoading(false));

    api.getMemberPerformance(20)
      .then(setMembers)
      .catch((e) => setMembersError(e.message ?? 'Failed to load'))
      .finally(() => setMembersLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-100">Analytics</h1>
        <Link to="/dashboard" className="text-sm text-blue-400 hover:underline">
          &larr; Back to Dashboard
        </Link>
      </div>

      {/* Party Comparison */}
      <SectionCard title="Party Trading Comparison" loading={partyLoading}>
        {partyError ? <ErrorMsg msg={partyError} /> : partyData.length === 0 ? (
          <div className="text-slate-500 text-center py-8">No party data available</div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Trade Volume by Party */}
            <div>
              <div className="text-xs text-slate-400 uppercase tracking-wide mb-3">Trade Volume</div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={partyData} layout="vertical" margin={{ left: 8, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis type="number" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="party" stroke="#94a3b8" tick={{ fontSize: 12 }} width={30} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Legend />
                  <Bar dataKey="buy_count" name="Buys" stackId="a" fill="#22c55e" />
                  <Bar dataKey="sell_count" name="Sells" stackId="a" fill="#ef4444" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Avg Anomaly Score by Party */}
            <div>
              <div className="text-xs text-slate-400 uppercase tracking-wide mb-3">Avg Anomaly Score</div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={partyData} layout="vertical" margin={{ left: 8, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis type="number" stroke="#94a3b8" tick={{ fontSize: 11 }} domain={[0, 100]} />
                  <YAxis type="category" dataKey="party" stroke="#94a3b8" tick={{ fontSize: 12 }} width={30} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Bar dataKey="avg_anomaly_score" name="Avg Anomaly" radius={[0, 4, 4, 0]}>
                    {partyData.map((entry) => (
                      <Cell key={entry.party} fill={PARTY_COLORS[entry.party] ?? '#94a3b8'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Summary stats table */}
            <div className="lg:col-span-2 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-400 border-b border-slate-700">
                    <th className="pb-2 font-medium">Party</th>
                    <th className="pb-2 font-medium text-right">Trades</th>
                    <th className="pb-2 font-medium text-right">Members</th>
                    <th className="pb-2 font-medium text-right">Tickers</th>
                    <th className="pb-2 font-medium text-right">Avg Anomaly</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {partyData.map((row) => (
                    <tr key={row.party} className="text-slate-300">
                      <td className="py-2">
                        <PartyBadge party={row.party} />
                      </td>
                      <td className="py-2 text-right font-mono">{row.trade_count.toLocaleString()}</td>
                      <td className="py-2 text-right font-mono">{row.unique_members}</td>
                      <td className="py-2 text-right font-mono">{row.unique_tickers}</td>
                      <td className="py-2 text-right">
                        <AnomalyBadge score={row.avg_anomaly_score} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </SectionCard>

      {/* Top 20 Tickers */}
      <SectionCard title="Top 20 Most Traded Tickers" loading={tickersLoading}>
        {tickersError ? <ErrorMsg msg={tickersError} /> : topTickers.length === 0 ? (
          <div className="text-slate-500 text-center py-8">No ticker data available</div>
        ) : (
          <ResponsiveContainer width="100%" height={420}>
            <BarChart
              data={topTickers}
              layout="vertical"
              margin={{ top: 0, right: 12, left: 4, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" stroke="#94a3b8" tick={{ fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="ticker"
                stroke="#94a3b8"
                tick={{ fontSize: 11 }}
                width={56}
              />
              <Tooltip
                {...TOOLTIP_STYLE}
                formatter={(value, name) => [Number(value ?? 0).toLocaleString(), String(name)]}
              />
              <Legend />
              <Bar dataKey="buy_count" name="Buys" stackId="a" fill="#22c55e" />
              <Bar dataKey="sell_count" name="Sells" stackId="a" fill="#ef4444" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </SectionCard>

      {/* Disclosure Delay Histogram */}
      <SectionCard title="Disclosure Delay Distribution (STOCK Act: 45-day limit)" loading={delaysLoading}>
        {delaysError ? <ErrorMsg msg={delaysError} /> : delays.length === 0 ? (
          <div className="text-slate-500 text-center py-8">No delay data available</div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={delays} margin={{ top: 0, right: 12, left: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="bucket" stroke="#94a3b8" tick={{ fontSize: 11 }} />
              <YAxis stroke="#94a3b8" tick={{ fontSize: 11 }} />
              <Tooltip
                {...TOOLTIP_STYLE}
                formatter={(value) => [Number(value ?? 0).toLocaleString(), 'Filings']}
              />
              <Bar dataKey="count" name="Filings" radius={[4, 4, 0, 0]}>
                {delays.map((entry) => (
                  <Cell
                    key={entry.bucket}
                    fill={entry.min_days > 45 ? '#ef4444' : entry.min_days > 30 ? '#f59e0b' : '#3b82f6'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </SectionCard>

      {/* Member Performance Table */}
      <SectionCard title="Member Performance by Anomaly Score" loading={membersLoading}>
        {membersError ? <ErrorMsg msg={membersError} /> : members.length === 0 ? (
          <div className="text-slate-500 text-center py-8">No member data available</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-400 border-b border-slate-700">
                  <th className="pb-2 font-medium w-8">#</th>
                  <th className="pb-2 font-medium">Name</th>
                  <th className="pb-2 font-medium">State</th>
                  <th className="pb-2 font-medium">Chamber</th>
                  <th className="pb-2 font-medium text-right">Trades</th>
                  <th className="pb-2 font-medium text-right">Avg Score</th>
                  <th className="pb-2 font-medium text-right">Max Score</th>
                  <th className="pb-2 font-medium text-right">High Anomaly</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {members.map((m, idx) => (
                  <tr key={m.bioguide_id} className="hover:bg-slate-700/30 transition-colors">
                    <td className="py-2 text-slate-500 font-mono">{idx + 1}</td>
                    <td className="py-2">
                      <div className="flex items-center gap-2">
                        <Link
                          to={`/members/${m.bioguide_id}`}
                          className="text-blue-400 hover:underline"
                        >
                          {m.name}
                        </Link>
                        <PartyBadge party={m.party} />
                      </div>
                    </td>
                    <td className="py-2 text-slate-400">{m.state}</td>
                    <td className="py-2 text-slate-400 capitalize">{m.chamber}</td>
                    <td className="py-2 text-right font-mono text-slate-300">{m.trade_count}</td>
                    <td className="py-2 text-right">
                      <AnomalyBadge score={m.avg_anomaly_score} />
                    </td>
                    <td className="py-2 text-right">
                      <AnomalyBadge score={m.max_anomaly_score} />
                    </td>
                    <td className="py-2 text-right font-mono text-amber-400">{m.high_anomaly_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
