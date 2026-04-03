import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import TradeFeed from './pages/TradeFeed';
import Dashboard from './pages/Dashboard';
import MemberProfile from './pages/MemberProfile';

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
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
