export const EMOJI = {
  BTC: '₿', ETH: '⟠', SOL: '◎', DOGE: '🐕', XRP: '💧',
  AAPL: '🍎', TSLA: '🚗', NVDA: '💻', MSFT: '☁️', AMZN: '📦',
  META: '📱', GOOGL: '🔍', GOOG: '🔍', NFLX: '🎬', AMD: '💻',
  MSTR: '₿', COIN: '💰', GME: '🎮', AMC: '🎬', PLTR: '🛰️',
  RIVN: '🚗', NIO: '🚗', SNAP: '📱', MARA: '⛏️', RIOT: '⛏️',
  ARM: '💻', SMCI: '🖥️', NOW: '☁️', UBER: '🚗', HOOD: '📊',
  RBLX: '🎮', SPOT: '🎵', DIS: '🏰', BA: '✈️', F: '🚗',
};

export function tEmoji(ticker, dir) {
  return EMOJI[ticker] || (dir === 'long' ? '📈' : '📉');
}

export function timeAgo(iso) {
  if (!iso) return '';
  const d = new Date(iso), now = new Date();
  const days = Math.floor((now - d) / 864e5);
  if (days === 0) return 'today';
  if (days === 1) return '1d ago';
  if (days < 7) return days + 'd ago';
  if (days < 31) return Math.floor(days / 7) + 'w ago';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function fmtPnl(v) {
  if (v == null) return '—';
  return (v >= 0 ? '+$' : '-$') + Math.abs(v).toFixed(2);
}
export function fmtPct(v) {
  if (v == null) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
}
export function pnlCls(v) { return v == null ? '' : v >= 0 ? 'pos' : 'neg'; }
export function pnlBgCls(v) { return v == null ? '' : v >= 0 ? 'pos-bg' : 'neg-bg'; }
export function firstName(name) { return (name || '').trim().split(' ')[0]; }

export function xLabel(dateStr) {
  if (!dateStr) return '';
  // Today's intraday points are full ISO timestamps (contain 'T'); historical
  // points are plain "YYYY-MM-DD" dates and need the time appended to parse
  // in the local timezone instead of UTC.
  const isIntraday = dateStr.includes('T');
  const d = isIntraday ? new Date(dateStr) : new Date(dateStr + 'T00:00:00');
  if (isIntraday) return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/** Market status Mon–Fri 9:30–16:00 America/New_York. */
export function marketStatus() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', hour12: false, weekday: 'short', hour: '2-digit', minute: '2-digit',
  }).formatToParts(new Date());
  const map = {};
  parts.forEach((p) => { map[p.type] = p.value; });
  const mins = parseInt(map.hour, 10) * 60 + parseInt(map.minute, 10);
  const isWeekday = !['Sat', 'Sun'].includes(map.weekday);
  if (!isWeekday) return { label: 'Market Closed', color: '#a39fb0' };
  if (mins < 9 * 60 + 30) return { label: 'Pre-Market', color: '#7c3aed' };
  if (mins >= 16 * 60) return { label: 'After Hours', color: '#a39fb0' };
  return { label: 'Market Open', color: '#16a34a' };
}
