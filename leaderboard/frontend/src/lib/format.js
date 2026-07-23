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

/**
 * mode: 'time' -> "9:34 AM", 'date' -> "Jul 21", 'datetime' -> "Jul 21, 9:34 AM".
 * Points are usually full ISO timestamps (contain 'T'); a few legacy points
 * from before intraday history existed are plain "YYYY-MM-DD" dates and need
 * the time appended to parse in the local timezone instead of UTC.
 */
export function xLabel(dateStr, mode = 'time') {
  if (!dateStr) return '';
  const isIntraday = dateStr.includes('T');
  const d = isIntraday ? new Date(dateStr) : new Date(dateStr + 'T00:00:00');
  const datePart = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  if (!isIntraday || mode === 'date') return datePart;
  const timePart = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  if (mode === 'datetime') return `${datePart}, ${timePart}`;
  return timePart;
}

/**
 * Shared session-window logic for a market's local time-of-day, given a
 * list of [openMinute, closeMinute) trading sessions (more than one for
 * exchanges with a midday break, e.g. Bursa Malaysia).
 */
function _sessionStatus(mins, isWeekday, sessions) {
  if (!isWeekday) return { label: 'Market Closed', color: '#a39fb0' };
  if (mins < sessions[0][0]) return { label: 'Pre-Market', color: '#7c3aed' };
  for (const [open, close] of sessions) {
    if (mins >= open && mins < close) return { label: 'Market Open', color: '#16a34a' };
  }
  if (mins >= sessions[sessions.length - 1][1]) return { label: 'After Hours', color: '#a39fb0' };
  return { label: 'Lunch Break', color: '#a39fb0' };
}

function _localMinutes(timeZone) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone, hour12: false, weekday: 'short', hour: '2-digit', minute: '2-digit',
  }).formatToParts(new Date());
  const map = {};
  parts.forEach((p) => { map[p.type] = p.value; });
  return {
    mins: parseInt(map.hour, 10) * 60 + parseInt(map.minute, 10),
    isWeekday: !['Sat', 'Sun'].includes(map.weekday),
  };
}

/** US market status Mon–Fri 9:30–16:00 America/New_York. */
export function marketStatusUS() {
  const { mins, isWeekday } = _localMinutes('America/New_York');
  return _sessionStatus(mins, isWeekday, [[9 * 60 + 30, 16 * 60]]);
}

/** Bursa Malaysia status Mon–Fri 9:00–12:30 & 14:30–17:00 Asia/Kuala_Lumpur. */
export function marketStatusMY() {
  const { mins, isWeekday } = _localMinutes('Asia/Kuala_Lumpur');
  return _sessionStatus(mins, isWeekday, [[9 * 60, 12 * 60 + 30], [14 * 60 + 30, 17 * 60]]);
}

/** HKEX status Mon–Fri 9:30–12:00 & 13:00–16:00 Asia/Hong_Kong. */
export function marketStatusHK() {
  const { mins, isWeekday } = _localMinutes('Asia/Hong_Kong');
  return _sessionStatus(mins, isWeekday, [[9 * 60 + 30, 12 * 60], [13 * 60, 16 * 60]]);
}
