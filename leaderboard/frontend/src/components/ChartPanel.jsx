import { useEffect, useMemo, useRef, useState } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
} from 'chart.js';
import { firstName, marketStatusMY, marketStatusUS, xLabel } from '../lib/format';
import { zeroLinePlugin, makeEndLabelPlugin } from '../lib/chartPlugins';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip);

const parseDate = (s) => (s.includes('T') ? new Date(s) : new Date(`${s}T00:00:00`));

function buildChartData(users, tf, mode, hidden, isMobile) {
  const dateSet = new Set();
  users.forEach((u) => u.equity_curve.forEach((p) => dateSet.add(p.date)));
  let dates = [...dateSet].sort();

  // Points are now dense intraday buckets rather than one-per-day, so 1W/1M
  // filter by actual elapsed time from the most recent point, not by
  // slicing the last N array entries (which used to mean "N days" back
  // when there was only one point per day).
  if (dates.length && (tf === '1W' || tf === '1M')) {
    const lastMs = parseDate(dates[dates.length - 1]).getTime();
    const windowMs = (tf === '1W' ? 7 : 30) * 24 * 3600 * 1000;
    const cutoff = lastMs - windowMs;
    dates = dates.filter((d) => parseDate(d).getTime() >= cutoff);
  }

  let series = users.map((u) => {
    const byDate = {};
    u.equity_curve.forEach((p) => { byDate[p.date] = p.equity; });
    let vals = dates.map((d) => (d in byDate ? byDate[d] : null));
    if (mode === '%') {
      const notional = Math.max((u.idea_count || 0) * 1000, 1000);
      vals = vals.map((v) => (v != null ? (v / notional) * 100 : null));
    }
    return { user: u, vals };
  });

  // Mobile screens are much narrower than desktop — the same point density
  // reads as a cramped zigzag instead of a smooth line. Halve it: merge
  // consecutive points in pairs, averaging each user's values per pair, so
  // the mobile chart still looks natural rather than just being squeezed.
  if (isMobile && dates.length > 20) {
    const factor = 2;
    const newDates = [];
    const merged = series.map(() => []);
    for (let i = 0; i < dates.length; i += factor) {
      const end = Math.min(i + factor, dates.length);
      newDates.push(dates[end - 1]);
      series.forEach((s, si) => {
        const chunk = s.vals.slice(i, end).filter((v) => v != null);
        merged[si].push(chunk.length ? chunk.reduce((a, b) => a + b, 0) / chunk.length : null);
      });
    }
    dates = newDates;
    series = series.map((s, si) => ({ user: s.user, vals: merged[si] }));
  }

  const datasets = series.map(({ user: u, vals }) => ({
    label: u.display_name,
    data: vals,
    borderColor: u.color,
    backgroundColor: 'transparent',
    tension: 0.3,
    pointRadius: 0,
    borderWidth: 2.5,
    spanGaps: true,
    hidden: hidden.has(u.telegram_user_id),
  }));

  return { labels: dates, datasets };
}

export default function ChartPanel({ users }) {
  const [mode, setMode] = useState('%');
  const [tf, setTf] = useState('ALL');
  const [hidden, setHidden] = useState(() => new Set());
  const [statusUS, setStatusUS] = useState(marketStatusUS());
  const [statusMY, setStatusMY] = useState(marketStatusMY());
  const [avatarImages, setAvatarImages] = useState({});

  // react-chartjs-2 binds the `plugins` prop's functions once at chart
  // creation and never re-binds them on updates, so the plugin reads live
  // values through this ref (kept in sync every render) rather than being
  // recreated with fresh closures each time users/mode/avatarImages change.
  const liveRef = useRef({ users, mode, avatarImages });
  liveRef.current = { users, mode, avatarImages };

  useEffect(() => {
    const id = setInterval(() => {
      setStatusUS(marketStatusUS());
      setStatusMY(marketStatusMY());
    }, 60000);
    return () => clearInterval(id);
  }, []);

  // Preload each trader's Telegram photo once for the chart's end-label
  // avatars (canvas needs an already-loaded <img>, not a URL).
  useEffect(() => {
    users.forEach((u) => {
      if (!u.photo_url || avatarImages[u.telegram_user_id]) return;
      const img = new Image();
      img.onload = () => setAvatarImages((prev) => ({ ...prev, [u.telegram_user_id]: img }));
      img.src = u.photo_url;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [users]);

  function toggleUser(uid) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid); else next.add(uid);
      return next;
    });
  }

  const isMobile = typeof window !== 'undefined' && window.innerWidth <= 760;
  const chartData = useMemo(
    () => buildChartData(users, tf, mode, hidden, isMobile),
    [users, tf, mode, hidden, isMobile],
  );

  // Points now span anywhere from a few minutes to several months, so tick
  // labels adapt: show a bare time when the whole visible range fits in a
  // day, otherwise show the date (tooltips always show both).
  const tickMode = useMemo(() => {
    const dates = chartData.labels;
    if (dates.length < 2) return 'time';
    const spanMs = parseDate(dates[dates.length - 1]) - parseDate(dates[0]);
    return spanMs > 36 * 3600 * 1000 ? 'date' : 'time';
  }, [chartData.labels]);

  const options = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 350 },
    interaction: { mode: 'index', intersect: false },
    layout: { padding: { right: isMobile ? 78 : 160, left: 2, top: 10, bottom: 4 } },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#ffffff',
        borderColor: '#eae7f3',
        borderWidth: 1,
        titleColor: '#181521',
        bodyColor: '#6b6478',
        titleFont: { family: 'Sora, sans-serif', weight: '700', size: 13 },
        bodyFont: { family: 'IBM Plex Mono, monospace', size: 12 },
        padding: 12,
        callbacks: {
          title(items) { return xLabel(items[0]?.label, 'datetime'); },
          label(ctx) {
            const v = ctx.parsed.y;
            if (v == null) return null;
            const name = ctx.dataset.label;
            if (mode === '%') return ` ${name}: ${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
            return ` ${name}: ${v >= 0 ? '+$' : '-$'}${Math.abs(v).toFixed(2)}`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: '#a39fb0',
          font: { family: 'IBM Plex Mono, monospace', size: isMobile ? 9 : 11 },
          maxTicksLimit: isMobile ? 4 : 6,
          maxRotation: 0,
          autoSkipPadding: isMobile ? 12 : 0,
          callback(val) { return xLabel(this.getLabelForValue(val), tickMode); },
        },
        grid: { color: '#f0eef7', lineWidth: 1 },
        border: { color: '#eae7f3' },
      },
      y: {
        ticks: {
          color: '#6b6478',
          font: { family: 'IBM Plex Mono, monospace', size: 12, weight: '600' },
          callback(v) {
            if (mode === '%') return (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
            return (v >= 0 ? '+$' : '-$') + Math.abs(v).toFixed(0);
          },
        },
        grid: { color: '#f0eef7', lineWidth: 1 },
        border: { color: '#eae7f3' },
      },
    },
  }), [mode, isMobile, tickMode]);

  // Stable forever — liveRef never changes identity, and the plugin reads
  // liveRef.current at draw time, so it doesn't need to be recreated.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const plugins = useMemo(() => [zeroLinePlugin, makeEndLabelPlugin(liveRef)], []);

  return (
    <div className="panel chart-panel">
      <div className="chart-top">
        <div className="chart-top-left">
          <div className="chart-title">
            <span className="chart-dot" />
            <h2>Total P&amp;L</h2>
          </div>
          <div className="toggle-group">
            <button className={`toggle-btn ${mode === '$' ? 'active' : ''}`} onClick={() => setMode('$')}>$</button>
            <button className={`toggle-btn ${mode === '%' ? 'active' : ''}`} onClick={() => setMode('%')}>%</button>
          </div>
          <div className="toggle-group">
            <button className={`toggle-btn ${tf === 'ALL' ? 'active' : ''}`} onClick={() => setTf('ALL')}>ALL</button>
            <button className={`toggle-btn ${tf === '1M' ? 'active' : ''}`} onClick={() => setTf('1M')}>1M</button>
            <button className={`toggle-btn ${tf === '1W' ? 'active' : ''}`} onClick={() => setTf('1W')}>1W</button>
          </div>
        </div>
        <div className="status-badge-group">
          <div className="status-badge">
            <span className="status-market">US</span>
            <span className="dot" style={{ background: statusUS.color }} />
            {statusUS.label}
          </div>
          <div className="status-badge">
            <span className="status-market">MSIA</span>
            <span className="dot" style={{ background: statusMY.color }} />
            {statusMY.label}
          </div>
        </div>
      </div>

      <div className="legend-chips" style={{ marginBottom: 12 }}>
        {users.map((u) => (
          <button
            key={u.telegram_user_id}
            className={`chip ${hidden.has(u.telegram_user_id) ? 'off' : ''}`}
            onClick={() => toggleUser(u.telegram_user_id)}
          >
            <span className="chip-dot" style={{ background: u.color }}>{u.initials}</span>
            <span className="chip-name">{firstName(u.display_name)}</span>
          </button>
        ))}
      </div>

      <div className="chart-wrap">
        <Line data={chartData} options={options} plugins={plugins} />
      </div>
    </div>
  );
}
