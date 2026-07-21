export const zeroLinePlugin = {
  id: 'zeroLine',
  beforeDatasetsDraw(chart) {
    const { ctx, chartArea: ca, scales: { y } } = chart;
    if (!ca || !y) return;
    const y0 = y.getPixelForValue(0);
    if (y0 < ca.top || y0 > ca.bottom) return;
    ctx.save();
    ctx.strokeStyle = '#d8d4e8';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 8]);
    ctx.beginPath();
    ctx.moveTo(ca.left, y0);
    ctx.lineTo(ca.right, y0);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  },
};

/** Draws avatar-circle + live P&L badges at the right edge of each line. */
export function makeEndLabelPlugin(users, mode) {
  return {
    id: 'endLabels',
    afterDraw(chart) {
      if (window.innerWidth <= 760) return;
      const { ctx, chartArea: ca } = chart;
      if (!ca) return;

      const pts = [];
      chart.data.datasets.forEach((ds, i) => {
        const meta = chart.getDatasetMeta(i);
        if (meta.hidden) return;
        let last = null, rawVal = null;
        for (let j = meta.data.length - 1; j >= 0; j--) {
          const pt = meta.data[j];
          if (pt && isFinite(pt.y)) { last = pt; rawVal = ds.data[j]; break; }
        }
        if (!last || rawVal == null) return;
        const user = users.find((u) => u.display_name === ds.label);
        if (!user) return;
        pts.push({ y: last.y, rawVal, user, color: ds.borderColor });
      });
      if (!pts.length) return;

      pts.sort((a, b) => a.y - b.y);
      const GAP = 24;
      for (let pass = 0; pass < 40; pass++) {
        let moved = false;
        for (let k = 1; k < pts.length; k++) {
          if (pts[k].y - pts[k - 1].y < GAP) {
            const mid = (pts[k - 1].y + pts[k].y) / 2;
            pts[k - 1].y = Math.max(ca.top + 12, mid - GAP / 2);
            pts[k].y = Math.min(ca.bottom - 8, mid + GAP / 2);
            moved = true;
          }
        }
        if (!moved) break;
      }

      ctx.save();
      pts.forEach(({ y, rawVal, user, color }) => {
        const x = ca.right + 8;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x + 11, y, 11, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 8px IBM Plex Mono, monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(user.initials, x + 11, y);

        const label = mode === '%'
          ? (rawVal >= 0 ? '+' : '') + rawVal.toFixed(1) + '%'
          : (rawVal >= 0 ? '+$' : '-$') + Math.abs(rawVal).toFixed(0);
        ctx.fillStyle = rawVal >= 0 ? '#16a34a' : '#e11d48';
        ctx.font = 'bold 11px IBM Plex Mono, monospace';
        ctx.textAlign = 'left';
        ctx.fillText(label, x + 25, y);
      });
      ctx.restore();
    },
  };
}
