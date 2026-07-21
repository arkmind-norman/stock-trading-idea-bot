import Avatar from './Avatar';
import { fmtPnl, pnlBgCls } from '../lib/format';

export default function RankedPanel({ users, selected, onSelect }) {
  return (
    <div className="panel ranked-panel">
      <div className="panel-hdr">
        <h2>Leaderboard</h2>
        <p>ranked by total P&amp;L</p>
      </div>
      {!users.length ? (
        <div className="empty">No data yet.<br />Post a trade idea in Telegram to get started!</div>
      ) : (
        users.map((u) => (
          <div
            key={u.telegram_user_id}
            className={`rk-row ${selected === u.telegram_user_id ? 'active' : ''}`}
            onClick={() => onSelect(u.telegram_user_id)}
          >
            <div className="rk-rank">#{u.rank}</div>
            <Avatar user={u} className="rk-avatar" />
            <div className="rk-info">
              <div className="rk-name">{u.display_name}</div>
              <div className="rk-sub">{(u.win_rate * 100).toFixed(0)}% win rate · {u.idea_count} calls</div>
            </div>
            <span className={`pnl-pill ${pnlBgCls(u.pnl)}`}>{fmtPnl(u.pnl)}</span>
            <button
              className="view-btn"
              onClick={(e) => { e.stopPropagation(); onSelect(u.telegram_user_id); }}
            >
              View
            </button>
          </div>
        ))
      )}
    </div>
  );
}
