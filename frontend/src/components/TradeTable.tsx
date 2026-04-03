import { Link } from 'react-router-dom';
import type { Trade } from '../api/client';
import PartyBadge from './PartyBadge';
import TradeTypeBadge from './TradeTypeBadge';
import AnomalyBadge from './AnomalyBadge';

interface TradeTableProps {
  trades: Trade[];
  loading?: boolean;
  showPolitician?: boolean;
}

export default function TradeTable({ trades, loading, showPolitician = true }: TradeTableProps) {
  if (loading) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
        <div className="animate-pulse p-4 space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-10 bg-slate-700 rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (trades.length === 0) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-8 text-center text-slate-400">
        No trades found.
      </div>
    );
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-left">
              <th className="px-4 py-3 text-slate-400 font-medium">Date</th>
              {showPolitician && (
                <th className="px-4 py-3 text-slate-400 font-medium">Politician</th>
              )}
              <th className="px-4 py-3 text-slate-400 font-medium">Party</th>
              <th className="px-4 py-3 text-slate-400 font-medium">Ticker</th>
              <th className="px-4 py-3 text-slate-400 font-medium">Type</th>
              <th className="px-4 py-3 text-slate-400 font-medium">Amount</th>
              <th className="px-4 py-3 text-slate-400 font-medium">Anomaly</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade, idx) => (
              <tr
                key={trade.id ?? idx}
                className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors"
              >
                <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                  {trade.transaction_date}
                </td>
                {showPolitician && (
                  <td className="px-4 py-3">
                    {trade.bioguide_id ? (
                      <Link
                        to={`/members/${trade.bioguide_id}`}
                        className="text-blue-400 hover:text-blue-300 hover:underline"
                      >
                        {trade.politician}
                      </Link>
                    ) : (
                      <span className="text-slate-200">{trade.politician}</span>
                    )}
                  </td>
                )}
                <td className="px-4 py-3">
                  <PartyBadge party={trade.party} />
                </td>
                <td className="px-4 py-3 font-mono text-slate-200 font-medium">
                  {trade.ticker}
                </td>
                <td className="px-4 py-3">
                  <TradeTypeBadge type={trade.trade_type} />
                </td>
                <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                  {trade.amount_range}
                </td>
                <td className="px-4 py-3">
                  <AnomalyBadge score={trade.anomaly_score} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
