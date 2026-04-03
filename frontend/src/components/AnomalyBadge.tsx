interface AnomalyBadgeProps {
  score: number | undefined | null;
}

export default function AnomalyBadge({ score }: AnomalyBadgeProps) {
  if (score == null) {
    return <span className="text-slate-500 text-sm">--</span>;
  }

  let color: string;
  if (score <= 30) {
    color = 'bg-green-500/20 text-green-400';
  } else if (score <= 60) {
    color = 'bg-yellow-500/20 text-yellow-400';
  } else if (score <= 80) {
    color = 'bg-orange-500/20 text-orange-400';
  } else {
    color = 'bg-red-500/20 text-red-400';
  }

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold ${color}`}>
      {Math.round(score)}
    </span>
  );
}
