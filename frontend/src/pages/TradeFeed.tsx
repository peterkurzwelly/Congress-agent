import { useEffect, useState, useCallback } from 'react';
import { api, type Trade, type TradesResponse } from '../api/client';
import StatsBar from '../components/StatsBar';
import TradeTable from '../components/TradeTable';
import Pagination from '../components/Pagination';

export default function TradeFeed() {
  const [data, setData] = useState<TradesResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState('');
  const [chamber, setChamber] = useState('');
  const [party, setParty] = useState('');
  const [tradeType, setTradeType] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 25;

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number | undefined> = {
        offset,
        limit,
        chamber: chamber || undefined,
        party: party || undefined,
        trade_type: tradeType || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        politician: search || undefined,
      };
      const result = await api.getTrades(params);
      setData(result);
    } catch (err) {
      console.error('Failed to fetch trades:', err);
    } finally {
      setLoading(false);
    }
  }, [offset, chamber, party, tradeType, dateFrom, dateTo, search]);

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades]);

  // Reset offset when filters change
  useEffect(() => {
    setOffset(0);
  }, [search, chamber, party, tradeType, dateFrom, dateTo]);

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-100 mb-6">Trade Feed</h1>

      <StatsBar />

      {/* Filters */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
          <input
            type="text"
            placeholder="Search politician..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 lg:col-span-2"
          />
          <select
            value={chamber}
            onChange={(e) => setChamber(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
          >
            <option value="">All Chambers</option>
            <option value="senate">Senate</option>
            <option value="house">House</option>
          </select>
          <select
            value={party}
            onChange={(e) => setParty(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
          >
            <option value="">All Parties</option>
            <option value="D">Democrat</option>
            <option value="R">Republican</option>
            <option value="I">Independent</option>
          </select>
          <select
            value={tradeType}
            onChange={(e) => setTradeType(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
          >
            <option value="">All Types</option>
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
          </select>
          <div className="flex gap-2 sm:col-span-2 lg:col-span-6">
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="flex-1 bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
              placeholder="From"
            />
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="flex-1 bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
              placeholder="To"
            />
          </div>
        </div>
      </div>

      <TradeTable trades={data?.trades ?? []} loading={loading} />

      {data && (
        <Pagination
          total={data.total}
          offset={data.offset}
          limit={data.limit}
          onPageChange={setOffset}
        />
      )}
    </div>
  );
}
