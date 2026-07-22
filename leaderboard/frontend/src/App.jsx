import { useEffect, useRef, useState } from 'react';
import { fetchLeaderboard } from './lib/api';
import InfoPanel from './components/InfoPanel';
import RankedPanel from './components/RankedPanel';
import ChartPanel from './components/ChartPanel';
import ChatPanel from './components/ChatPanel';
import PortfolioPanel from './components/PortfolioPanel';

// Data refetches every 5s from our own API (cheap — just a DB read); the
// backend independently pulls fresh prices from yfinance every 1 minute
// during market hours and persists them, so refreshes in between simply
// repeat the latest known values until the next backend tick lands.
export default function App() {
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);
  const firstLoad = useRef(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const d = await fetchLeaderboard();
        if (cancelled) return;
        setData(d);
        setError(null);
        if (firstLoad.current && d.users.length) {
          setSelected(d.users[0].telegram_user_id);
          firstLoad.current = false;
        }
      } catch (err) {
        if (!cancelled) setError(err);
        console.error('Leaderboard load failed:', err);
      }
    }

    load();
    const id = setInterval(load, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <>
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark">📈</div>
          <div className="brand-name">Alpha Chat</div>
        </div>
        <div className="live-pill">
          <span className="live-dot" />
          <span>Live simulation</span>
        </div>
      </div>

      <div id="app">
        {error && !data ? (
          <div className="empty">⚠️ Couldn't load data.<br />Is the server running?</div>
        ) : (
          <>
            <div className="main-col">
              <InfoPanel traderCount={data?.users.length ?? 0} />
              <ChartPanel users={data?.users ?? []} />
            </div>
            <div className="side-col">
              <PortfolioPanel users={data?.users ?? []} feed={data?.feed ?? []} selected={selected} />
              <ChatPanel feed={data?.feed ?? []} onSelect={setSelected} />
            </div>
            <RankedPanel users={data?.users ?? []} selected={selected} onSelect={setSelected} />
          </>
        )}
      </div>
    </>
  );
}
