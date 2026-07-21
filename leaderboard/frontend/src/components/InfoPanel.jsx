export default function InfoPanel({ traderCount }) {
  return (
    <div className="panel info-panel">
      <h1>Idea Leaderboard</h1>
      <p className="sub">
        Friends drop stock calls in Telegram — the bot auto-sims the trade. This is who's actually printing.
      </p>
      <div className="meta-row">
        <div className="meta-icon">👥</div>
        <div className="meta-label">Traders</div>
        <div className="meta-val">{traderCount || '—'}</div>
      </div>
      <div className="meta-row">
        <div className="meta-icon">🎯</div>
        <div className="meta-label">Rule</div>
        <div className="meta-val">$1,000 fixed size · 10d default hold</div>
      </div>
      <div className="meta-row">
        <div className="meta-icon">💬</div>
        <div className="meta-label">Source</div>
        <div className="meta-val">Telegram group calls</div>
      </div>
    </div>
  );
}
