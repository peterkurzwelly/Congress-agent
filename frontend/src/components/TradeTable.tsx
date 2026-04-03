import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import type { Trade } from '../api/client';
import PartyBadge from './PartyBadge';
import TradeTypeBadge from './TradeTypeBadge';
import AnomalyBadge from './AnomalyBadge';

type SortKey = 'transaction_date' | 'politician' | 'ticker' | 'trade_type' | 'amount_range' | 'anomaly_score';
type SortDir = 'asc' | 'desc';

interface TradeTableProps {
  trades: Trade[];
  loading?: boolean;
  showPolitician?: boolean;
}

function isLateFiling(trade: Trade): boolean {
  if (!trade.transaction_date || !trade.disclosure_date) return false;
  const txDate = new Date(trade.transaction_date);
  const discDate = new Date(trade.disclosure_date);
  const diffDays = (discDate.getTime() - txDate.getTime()) / (1000 * 60 * 60 * 24);
  return diffDays > 45;
}

export default function TradeTable({ trades, loading, showPolitician = true }: TradeTableProps) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const sortedTrades = useMemo(() => {
    if (!sortKey) return trades;
    return [...trades].sort((a, b) => {
      const aVal = a[sortKey] ?? '';
      const bVal = b[sortKey] ?? '';
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
      }
      const cmp = String(aVal).localeCompare(String(bVal));
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [trades, sortKey, sortDir]);

  const sortIndicator = (key: SortKey) => {
    if (sortKey !== key) return <span className="text-slate-600 ml-1">{'\u2195'}</span>;
    return <span className="text-blue-400 ml-1">{sortDir === 'asc' ? '\u2191' : '\u2193'}</span>;
  };

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

  const thClass = "px-4 py-3 text-slate-400 font-medium cursor-pointer select-none hover:text-slate-200 transition-colors";

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-left">
              <th className={thClass} onClick={() => handleSort('transaction_date')}>
                Date{sortIndicator('transaction_date')}
              </th>
              {showPolitician && (
                <th className={thClass} onClick={() => handleSort('politician')}>
                  Politician{sortIndicator('politician')}
                </th>
              )}
              <th className="px-4 py-3 text-slate-400 font-medium">Party</th>
              <th className={thClass} onClick={() => handleSort('ticker')}>
                Ticker{sortIndicator('ticker')}
              </th>
              <th className={thClass} onClick={() => handleSort('trade_type')}>
                Type{sortIndicator('trade_type')}
              </th>
              <th className={thClass} onClick={() => handleSort('amount_range')}>
                Amount{sortIndicator('amount_range')}
              </th>
              <th className={thClass} onClick={() => handleSort('anomaly_score')}>
                Anomaly{sortIndicator('anomaly_score')}
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedTrades.map((trade, idx) => {
              const late = isLateFiling(trade);
              return (
                <tr
                  key={trade.id ?? idx}
                  className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors"
                >
                  <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                    <span className="flex items-center gap-1.5">
                      {trade.transaction_date}
                      {late && (
                        <span
                          className="inline-block w-2 h-2 rounded-full bg-red-500 flex-shrink-0"
                          title="Late filing (>45 days)"
                        />
                      )}
                    </span>
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
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
