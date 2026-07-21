import Avatar from './Avatar';
import { fmtPnl, pnlBgCls, firstName, tEmoji, timeAgo } from '../lib/format';

export default function ChatPanel({ feed, onSelect }) {
  return (
    <div className="panel chat-panel">
      <div className="panel-hdr">
        <h2>Idea Feed</h2>
        <p>every call posted to the chat, most recent first</p>
      </div>
      <div className="chat-list">
        {!feed.length ? (
          <div className="empty">No ideas posted yet.</div>
        ) : (
          feed.map((it, i) => {
            const em = tEmoji(it.ticker, it.direction);
            const label = it.company_name || it.ticker || '?';
            return (
              <div key={i} className="chat-item" onClick={() => onSelect(it.telegram_user_id)}>
                <div className="chat-item-hdr">
                  <Avatar user={it} className="chat-avatar" />
                  <span className="chat-name" style={{ color: it.color }}>{firstName(it.display_name)}</span>
                  <span className="chat-time">{timeAgo(it.submitted_at)}</span>
                </div>
                <div className="chat-body">
                  <b>{em} {label}</b> — "{it.raw_text || '...'}"
                </div>
                <span className={`chat-tag ${pnlBgCls(it.pnl_usd)}`}>{fmtPnl(it.pnl_usd)}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
