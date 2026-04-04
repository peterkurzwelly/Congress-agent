import { Link, useLocation } from 'react-router-dom';

const navLinks = [
  { to: '/', label: 'Trade Feed' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/watchlist', label: 'Watchlist' },
];

export default function Navbar() {
  const location = useLocation();

  return (
    <nav className="bg-slate-800 border-b border-slate-700 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          <Link to="/" className="flex items-center gap-2 text-lg font-bold text-slate-100 hover:text-blue-400 transition-colors">
            <span className="text-xl">🏛</span>
            <span className="hidden sm:inline">Congress Trades</span>
          </Link>
          <div className="flex gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  location.pathname === link.to
                    ? 'bg-slate-700 text-blue-400'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-700/50'
                }`}
              >
                {link.label}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </nav>
  );
}
