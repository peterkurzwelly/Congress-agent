import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, type Member, type Trade, type TradesResponse } from '../api/client';
import PartyBadge from '../components/PartyBadge';
import TradeTable from '../components/TradeTable';
import Pagination from '../components/Pagination';

export default function MemberProfile() {
  const { id } = useParams<{ id: string }>();
  const [member, setMember] = useState<Member | null>(null);
  const [tradesData, setTradesData] = useState<TradesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [tradesLoading, setTradesLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const limit = 25;

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api.getMember(id).then(setMember).catch(console.error).finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!member?.name) return;
    setTradesLoading(true);
    api
      .getTrades({ politician: member.name, offset, limit })
      .then(setTradesData)
      .catch(console.error)
      .finally(() => setTradesLoading(false));
  }, [member?.name, offset]);

  if (loading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-8 bg-slate-700 rounded w-48" />
        <div className="h-40 bg-slate-800 rounded-lg" />
      </div>
    );
  }

  if (!member) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl text-slate-300 mb-2">Member not found</h2>
        <Link to="/" className="text-blue-400 hover:underline">Back to Trade Feed</Link>
      </div>
    );
  }

  const chamberLabel = member.chamber === 'senate' ? 'Senator' : 'Representative';

  return (
    <div className="space-y-6">
      <Link to="/" className="text-blue-400 hover:underline text-sm">&larr; Back to Trade Feed</Link>

      {/* Member Info Card */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="w-16 h-16 bg-slate-700 rounded-full flex items-center justify-center text-2xl text-slate-400 font-bold">
            {member.name?.charAt(0) ?? '?'}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-bold text-slate-100">{member.name}</h1>
              <PartyBadge party={member.party} />
            </div>
            <div className="text-slate-400 mt-1">
              {chamberLabel} &middot; {member.state}
            </div>
            {member.committees && member.committees.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {member.committees.map((c) => (
                  <span key={c} className="px-2 py-1 bg-slate-700 text-slate-300 rounded text-xs">
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="text-right">
            <div className="text-slate-400 text-sm">Total Trades</div>
            <div className="text-3xl font-bold text-blue-400">
              {member.trade_count ?? member.total_trades ?? '--'}
            </div>
          </div>
        </div>
      </div>

      {/* Trade History */}
      <div>
        <h2 className="text-lg font-semibold text-slate-100 mb-4">Trade History</h2>
        <TradeTable trades={tradesData?.trades ?? []} loading={tradesLoading} showPolitician={false} />
        {tradesData && (
          <Pagination
            total={tradesData.total}
            offset={tradesData.offset}
            limit={tradesData.limit}
            onPageChange={setOffset}
          />
        )}
      </div>
    </div>
  );
}
