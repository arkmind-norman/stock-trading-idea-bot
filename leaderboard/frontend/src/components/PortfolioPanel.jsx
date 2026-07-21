import { useState } from 'react';
import Avatar from './Avatar';
import { fmtPnl, pnlCls, tEmoji } from '../lib/format';

export default function PortfolioPanel({ users, feed, selected }) {
  const [tab, setTab] = useState('positions');

  if (!users.length) {
    return (
      <div className="panel portfolio-panel">
        <div className="pf-list"><div className="empty">No traders yet.</div></div>
      </div>
    );
  }

  const user = users.find((u) => u.telegram_user_id === selected) || users[0];
  const userIdeas = feed.filter((f) => f.telegram_user_id === user.telegram_user_id);
  const open = userIdeas.filter((f) => f.status === 'open');
  const values = open.map((f) => 1000 + (f.pnl_usd || 0));
  const totalValue = values.reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="panel portfolio-panel">
      <div className="pf-hdr">
        <div className="pf-user">
          <Avatar user={user} className="pf-avatar" />
          <div className="pf-name">{user.display_name}</div>
        </div>
        <div className="tab-group">
          <button className={`tab-btn ${tab === 'positions' ? 'active' : ''}`} onClick={() => setTab('positions')}>Positions</button>
          <button className={`tab-btn ${tab === 'orders' ? 'active' : ''}`} onClick={() => setTab('orders')}>Orders</button>
        </div>
      </div>

      <div className="pf-stats">
        <div className="pf-stat">
          <div className={`pf-stat-val ${pnlCls(user.pnl)}`}>{fmtPnl(user.pnl)}</div>
          <div className="pf-stat-lbl">Total P&amp;L</div>
        </div>
        <div className="pf-stat">
          <div className={`pf-stat-val ${pnlCls(user.today_pnl)}`}>{user.today_pnl == null ? '—' : fmtPnl(user.today_pnl)}</div>
          <div className="pf-stat-lbl">Today's P&amp;L</div>
        </div>
        <div className="pf-stat">
          <div className="pf-stat-val">{(user.win_rate * 100).toFixed(0)}%</div>
          <div className="pf-stat-lbl">Win Rate</div>
        </div>
      </div>

      <div className="pf-list">
        {tab === 'positions' ? (
          !open.length ? (
            <div className="empty">No open positions.</div>
          ) : (
            <>
              <div className="pf-col-hdr">
                <span style={{ flex: 1.2 }}>Symbol</span>
                <span style={{ flex: 1, textAlign: 'right' }}>Weight</span>
                <span style={{ flex: 0.9, textAlign: 'right' }}>P&amp;L</span>
              </div>
              {open.map((f, i) => (
                <div className="pf-row" key={i}>
                  <span className="pf-sym">{tEmoji(f.ticker, f.direction)} {f.ticker || '?'}</span>
                  <span className="pf-mid">{((values[i] / totalValue) * 100).toFixed(1)}%</span>
                  <span className={`pf-pnl ${pnlCls(f.pnl_usd)}`}>{fmtPnl(f.pnl_usd)}</span>
                </div>
              ))}
            </>
          )
        ) : !userIdeas.length ? (
          <div className="empty">No orders yet.</div>
        ) : (
          <>
            <div className="pf-col-hdr">
              <span style={{ flex: 1.2 }}>Symbol</span>
              <span style={{ flex: 1, textAlign: 'right' }}>Entry → Now</span>
              <span style={{ flex: 0.9, textAlign: 'right' }}>P&amp;L</span>
            </div>
            {userIdeas.map((f, i) => (
              <div className="pf-row" key={i}>
                <span className="pf-sym">
                  <span className="pf-sym-label">{tEmoji(f.ticker, f.direction)} {f.ticker || '?'}</span>
                  <span
                    className={`pf-status ${f.status === 'open' ? 'pos-bg' : ''}`}
                    style={f.status === 'open' ? undefined : { background: '#f0eef7', color: '#a39fb0' }}
                  >
                    {f.status}
                  </span>
                </span>
                <span className="pf-mid">
                  {f.entry_price != null ? '$' + f.entry_price.toFixed(2) : '—'} → {f.current_price != null ? '$' + f.current_price.toFixed(2) : '—'}
                </span>
                <span className={`pf-pnl ${pnlCls(f.pnl_usd)}`}>{fmtPnl(f.pnl_usd)}</span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
