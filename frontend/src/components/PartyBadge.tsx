interface PartyBadgeProps {
  party: string;
  className?: string;
}

export default function PartyBadge({ party, className = '' }: PartyBadgeProps) {
  const colors: Record<string, string> = {
    D: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    R: 'bg-red-500/20 text-red-400 border-red-500/30',
    I: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  };

  const labels: Record<string, string> = {
    D: 'Democrat',
    R: 'Republican',
    I: 'Independent',
  };

  const key = party?.charAt(0).toUpperCase() ?? 'I';

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${
        colors[key] ?? colors.I
      } ${className}`}
    >
      {labels[key] ?? party}
    </span>
  );
}
