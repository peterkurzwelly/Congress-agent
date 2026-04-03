import { useEffect, useState } from 'react';
import { api, type Stats } from '../api/client';

export default function StatsBar() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    api.getStats().then(setStats).catch(console.error);
  }, []);

  if (!stats) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-slate-800 border border-slate-700 rounded-lg p-4 animate-pulse">
            <div className="h-4 bg-slate-700 rounded w-20 mb-2" />
            <div className="h-8 bg-slate-700 rounded w-16" />
          </div>
        ))}
      </div>
    );
  }

  const items = [
    { label: 'Total Trades', value: stats.total_trades.toLocaleString(), icon: '📊' },
    { label: 'Buys', value: stats.total_buys.toLocaleString(), icon: '🟢', color: 'text-green-400' },
    { label: 'Sells', value: stats.total_sells.toLocaleString(), icon: '🔴', color: 'text-red-400' },
    { label: 'Unique Tickers', value: stats.unique_tickers.toLocaleString(), icon: '🏷' },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {items.map((item) => (
        <div
          key={item.label}
          className="bg-slate-800 border border-slate-700 rounded-lg p-4"
        >
          <div className="text-slate-400 text-sm mb-1">{item.icon} {item.label}</div>
          <div className={`text-2xl font-bold ${item.color ?? 'text-slate-100'}`}>
            {item.value}
          </div>
        </div>
      ))}
    </div>
  );
}
