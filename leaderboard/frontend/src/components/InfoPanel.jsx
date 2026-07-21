export default function InfoPanel({ traderCount }) {
  return (
    <div className="panel info-panel">
      <div className="info-title">
        <h1>Idea Leaderboard</h1>
        <p className="sub">Friends drop stock calls in Telegram — the bot auto-sims the trade.</p>
      </div>
      <div className="info-meta">
        <div className="meta-item">
          <span className="meta-icon">👥</span>
          <span className="meta-val">{traderCount || '—'} traders</span>
        </div>
        <div className="meta-item">
          <span className="meta-icon">🎯</span>
          <span className="meta-val">$1,000 fixed · 10d hold</span>
        </div>
        <div className="meta-item">
          <span className="meta-icon">💬</span>
          <span className="meta-val">Telegram group calls</span>
        </div>
      </div>
    </div>
  );
}
