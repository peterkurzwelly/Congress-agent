import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import Navbar from './components/Navbar';
import TradeFeed from './pages/TradeFeed';
import Dashboard from './pages/Dashboard';
import MemberProfile from './pages/MemberProfile';
import Analytics from './pages/Analytics';
import Watchlist from './pages/Watchlist';

function NotFound() {
  return (
    <div className="text-center py-20">
      <div className="text-6xl font-bold text-slate-600 mb-4">404</div>
      <h1 className="text-xl text-slate-300 mb-2">Page Not Found</h1>
      <p className="text-slate-500 mb-6">The page you are looking for does not exist.</p>
      <Link to="/" className="text-blue-400 hover:underline">Back to Trade Feed</Link>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-900 text-slate-100">
        <Navbar />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <Routes>
            <Route path="/" element={<TradeFeed />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/members/:id" element={<MemberProfile />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
