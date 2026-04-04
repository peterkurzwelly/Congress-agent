import { useEffect, useState, useCallback } from 'react';
import { api, type WatchlistItem, type WatchlistMatchingTrade } from '../api/client';
import TradeTypeBadge from '../components/TradeTypeBadge';
import AnomalyBadge from '../components/AnomalyBadge';
import PartyBadge from '../components/PartyBadge';

function ErrorMsg({ msg }: { msg: string }) {
  return (
    <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-sm">
      {msg}
    </div>
  );
}

export default function Watchlist() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [recentTrades, setRecentTrades] = useState<WatchlistMatchingTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Add form state
  const [itemType, setItemType] = useState<'politician' | 'ticker'>('ticker');
  const [value, setValue] = useState('');
  const [notes, setNotes] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [addSuccess, setAddSuccess] = useState(false);

  // Delete state
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fetchWatchlist = useCallback(() => {
    setLoading(true);
    setFetchError(null);
    api.getWatchlist()
      .then((data) => {
        setItems(data.items ?? []);
        setRecentTrades(data.recent_trades ?? []);
      })
      .catch((e) => setFetchError(e.message ?? 'Failed to load watchlist'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchWatchlist();
  }, [fetchWatchlist]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) return;
    setAdding(true);
    setAddError(null);
    setAddSuccess(false);
    try {
      await api.addWatchlistItem(itemType, value.trim(), notes.trim() || undefined);
      setValue('');
      setNotes('');
      setAddSuccess(true);
      fetchWatchlist();
      setTimeout(() => setAddSuccess(false), 3000);
    } catch (e) {
      const err = e as Error;
      setAddError(err.message ?? 'Failed to add item');
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id: number) => {
    setDeletingId(id);
    setDeleteError(null);
    try {
      await api.deleteWatchlistItem(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch (e) {
      const err = e as Error;
      setDeleteError(err.message ?? 'Failed to delete item');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-100">Watchlist</h1>

      {/* Add Form */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
        <h2 className="text-lg font-semibold text-slate-100 mb-4">Add to Watchlist</h2>
        <form onSubmit={handleAdd} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-slate-400 uppercase tracking-wide mb-1">Type</label>
              <select
                value={itemType}
                onChange={(e) => setItemType(e.target.value as 'politician' | 'ticker')}
                className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500"
              >
                <option value="ticker">Ticker</option>
                <option value="politician">Politician</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 uppercase tracking-wide mb-1">
                {itemType === 'ticker' ? 'Ticker Symbol' : 'Politician Name'}
              </label>
              <input
                type="text"
                value={value}
                onChange={(e) => setValue(e.target.value.toUpperCase())}
                placeholder={itemType === 'ticker' ? 'e.g. NVDA' : 'e.g. Nancy Pelosi'}
                required
                className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 uppercase tracking-wide mb-1">Notes (optional)</label>
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Optional notes..."
                className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={adding || !value.trim()}
              className="px-5 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
            >
              {adding ? 'Adding...' : 'Add to Watchlist'}
            </button>
            {addSuccess && (
              <span className="text-green-400 text-sm">Added successfully!</span>
            )}
          </div>

          {addError && <ErrorMsg msg={addError} />}
        </form>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Watchlist Items */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">
            Watched Items
            {!loading && (
              <span className="ml-2 text-sm font-normal text-slate-400">({items.length})</span>
            )}
          </h2>

          {deleteError && <div className="mb-3"><ErrorMsg msg={deleteError} /></div>}

          {loading ? (
            <div className="animate-pulse space-y-2">
              {[1, 2, 3, 4].map((i) => <div key={i} className="h-12 bg-slate-700 rounded" />)}
            </div>
          ) : fetchError ? (
            <ErrorMsg msg={fetchError} />
          ) : items.length === 0 ? (
            <div className="text-slate-500 text-center py-8">
              No items in watchlist. Add a ticker or politician above.
            </div>
          ) : (
            <div className="space-y-2">
              {items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-3 rounded bg-slate-900/50 border border-slate-700"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                        item.item_type === 'ticker'
                          ? 'bg-blue-900/50 text-blue-300'
                          : 'bg-purple-900/50 text-purple-300'
                      }`}>
                        {item.item_type}
                      </span>
                      <span className="text-slate-100 font-mono font-medium">{item.value}</span>
                    </div>
                    {item.notes && (
                      <div className="text-xs text-slate-500 mt-0.5 truncate">{item.notes}</div>
                    )}
                    <div className="text-xs text-slate-600 mt-0.5">
                      Added {new Date(item.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(item.id)}
                    disabled={deletingId === item.id}
                    className="ml-3 p-1.5 rounded text-slate-500 hover:text-red-400 hover:bg-red-900/20 transition-colors disabled:opacity-50"
                    title="Remove from watchlist"
                  >
                    {deletingId === item.id ? (
                      <span className="text-xs">...</span>
                    ) : (
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Matching Trades */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">Recent Matching Trades</h2>
          {loading ? (
            <div className="animate-pulse space-y-2">
              {[1, 2, 3, 4].map((i) => <div key={i} className="h-14 bg-slate-700 rounded" />)}
            </div>
          ) : recentTrades.length === 0 ? (
            <div className="text-slate-500 text-center py-8">
              No recent trades match your watchlist items.
            </div>
          ) : (
            <div className="space-y-2">
              {recentTrades.map((trade, idx) => (
                <div
                  key={trade.id ?? idx}
                  className="p-3 rounded bg-slate-900/50 border border-slate-700"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-slate-100">{trade.ticker}</span>
                      <TradeTypeBadge type={trade.trade_type} />
                      {trade.anomaly_score !== undefined && (
                        <AnomalyBadge score={trade.anomaly_score} />
                      )}
                    </div>
                    <span className="text-xs text-slate-500">{trade.transaction_date}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-slate-300">{trade.politician}</span>
                    <PartyBadge party={trade.party} />
                    <span className="text-slate-500 text-xs">{trade.amount_range}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
