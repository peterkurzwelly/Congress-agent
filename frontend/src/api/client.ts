const BASE_URL = '/api';

export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly body?: string;

  constructor(status: number, statusText: string, body?: string) {
    super(`API error: ${status} ${statusText}`);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.body = body;
  }
}

async function request<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') {
        url.searchParams.set(key, String(value));
      }
    });
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    const body = await res.text().catch(() => undefined);
    throw new ApiError(res.status, res.statusText, body);
  }
  return res.json();
}

// Types
export interface Trade {
  id: string;
  politician: string;
  bioguide_id?: string;
  party: string;
  state: string;
  chamber: string;
  ticker: string;
  asset_name?: string;
  trade_type: string;
  amount_range: string;
  transaction_date: string;
  disclosure_date?: string;
  filing_url?: string;
  sector?: string;
  anomaly_score?: number;
  anomaly_reasons?: string[];
  committees?: string[];
}

export interface TradesResponse {
  trades: Trade[];
  total: number;
  offset: number;
  limit: number;
}

export interface Member {
  bioguide_id: string;
  name: string;
  party: string;
  state: string;
  chamber: string;
  trade_count: number;
  committees?: string[];
  total_trades?: number;
  recent_trades?: Trade[];
}

export interface Stats {
  total_trades: number;
  total_buys: number;
  total_sells: number;
  unique_tickers: number;
  unique_members: number;
  avg_anomaly_score?: number;
}

export interface SectorFlow {
  sector: string;
  net_flow: number;
  buy_volume: number;
  sell_volume: number;
  trade_count: number;
}

export interface TimelinePoint {
  date: string;
  count: number;
  buy_count?: number;
  sell_count?: number;
}

export interface ConcurrentTrade {
  ticker: string;
  members: string[];
  trade_type: string;
  date_range: string;
  count: number;
}

export interface PartyComparison {
  party: string;
  trade_count: number;
  buy_count: number;
  sell_count: number;
  avg_anomaly_score: number;
  unique_members: number;
  unique_tickers: number;
}

export interface TopTicker {
  ticker: string;
  trade_count: number;
  buy_count: number;
  sell_count: number;
  unique_members: number;
  sector?: string;
}

export interface DisclosureDelayBucket {
  bucket: string;
  count: number;
  min_days: number;
  max_days: number;
}

export interface MemberPerformance {
  bioguide_id: string;
  name: string;
  party: string;
  state: string;
  chamber: string;
  trade_count: number;
  avg_anomaly_score: number;
  max_anomaly_score: number;
  high_anomaly_count: number;
}

export interface WatchlistItem {
  id: number;
  item_type: string;
  value: string;
  created_at: string;
  notes?: string;
}

export interface WatchlistMatchingTrade extends Trade {
  watchlist_item_id: number;
}

export interface WatchlistResponse {
  items: WatchlistItem[];
  recent_trades?: WatchlistMatchingTrade[];
}

// API functions
export const api = {
  getTrades(params?: Record<string, string | number | undefined>): Promise<TradesResponse> {
    return request<TradesResponse>(`${BASE_URL}/trades/`, params);
  },

  getRecentTrades(): Promise<Trade[]> {
    return request<Trade[]>(`${BASE_URL}/trades/recent`);
  },

  getAnomalies(threshold = 50): Promise<Trade[]> {
    return request<Trade[]>(`${BASE_URL}/trades/anomalies`, { threshold });
  },

  getTrade(tradeId: string): Promise<Trade> {
    return request<Trade>(`${BASE_URL}/trades/${tradeId}`);
  },

  getMembers(): Promise<Member[]> {
    return request<Member[]>(`${BASE_URL}/members/`);
  },

  getTopTraders(limit = 10): Promise<Member[]> {
    return request<Member[]>(`${BASE_URL}/members/top-traders`, { limit });
  },

  getLateFilers(): Promise<Member[]> {
    return request<Member[]>(`${BASE_URL}/members/late-filers`);
  },

  getMember(bioguideId: string): Promise<Member> {
    return request<Member>(`${BASE_URL}/members/${bioguideId}`);
  },

  getStats(): Promise<Stats> {
    return request<Stats>(`${BASE_URL}/analytics/stats`);
  },

  getSectorFlows(): Promise<SectorFlow[]> {
    return request<SectorFlow[]>(`${BASE_URL}/analytics/sector-flows`);
  },

  getTimeline(dateFrom?: string, dateTo?: string): Promise<TimelinePoint[]> {
    return request<TimelinePoint[]>(`${BASE_URL}/analytics/timeline`, {
      date_from: dateFrom,
      date_to: dateTo,
    });
  },

  getConcurrent(days = 7): Promise<ConcurrentTrade[]> {
    return request<ConcurrentTrade[]>(`${BASE_URL}/analytics/concurrent`, { days });
  },

  getPartyComparison(): Promise<PartyComparison[]> {
    return request<PartyComparison[]>(`${BASE_URL}/analytics/party-comparison`);
  },

  getTopTickers(limit = 20, days?: number): Promise<TopTicker[]> {
    return request<TopTicker[]>(`${BASE_URL}/analytics/top-tickers`, { limit, days });
  },

  getDisclosureDelays(): Promise<DisclosureDelayBucket[]> {
    return request<DisclosureDelayBucket[]>(`${BASE_URL}/analytics/disclosure-delays`);
  },

  getMemberPerformance(limit = 20, minTrades?: number): Promise<MemberPerformance[]> {
    return request<MemberPerformance[]>(`${BASE_URL}/analytics/member-performance`, {
      limit,
      min_trades: minTrades,
    });
  },

  getWatchlist(): Promise<WatchlistResponse> {
    return request<WatchlistResponse>(`${BASE_URL}/watchlist`);
  },

  addWatchlistItem(item_type: string, value: string, notes?: string): Promise<WatchlistItem> {
    return fetch(`${BASE_URL}/watchlist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_type, value, notes }),
    }).then(async (res) => {
      if (!res.ok) {
        const body = await res.text().catch(() => undefined);
        throw new ApiError(res.status, res.statusText, body);
      }
      return res.json();
    });
  },

  deleteWatchlistItem(id: number): Promise<void> {
    return fetch(`${BASE_URL}/watchlist/${id}`, { method: 'DELETE' }).then(async (res) => {
      if (!res.ok) {
        const body = await res.text().catch(() => undefined);
        throw new ApiError(res.status, res.statusText, body);
      }
    });
  },
};
