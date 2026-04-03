interface TradeTypeBadgeProps {
  type: string;
}

export default function TradeTypeBadge({ type }: TradeTypeBadgeProps) {
  const isBuy = type?.toLowerCase().includes('buy') || type?.toLowerCase().includes('purchase');
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold ${
        isBuy
          ? 'bg-green-500/20 text-green-400'
          : 'bg-red-500/20 text-red-400'
      }`}
    >
      {isBuy ? 'BUY' : 'SELL'}
    </span>
  );
}
