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

function roundRectPath(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

const AVATAR_R = 16;
const PILL_H = 32;
const PILL_PAD = 14;

/**
 * Draws a solid-color pill (white bold value text) with a circular avatar
 * overlapping its left edge — avatarImages maps telegram_user_id to a
 * preloaded, already-complete HTMLImageElement; falls back to initials on a
 * solid-color circle when no photo is loaded yet.
 *
 * Takes a ref (not the values directly): react-chartjs-2 registers the
 * `plugins` prop's functions once at chart creation and does not re-bind
 * them on prop updates, so a plugin built from plain closures over
 * users/mode/avatarImages would keep seeing whatever those were on the
 * very first render forever. Reading live.current instead means the same
 * stable plugin object always sees the latest values.
 */
export function makeEndLabelPlugin(liveRef) {
  return {
    id: 'endLabels',
    afterDraw(chart) {
      if (window.innerWidth <= 760) return;
      const { users, mode, avatarImages } = liveRef.current;
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
      const GAP = PILL_H + 8;
      for (let pass = 0; pass < 40; pass++) {
        let moved = false;
        for (let k = 1; k < pts.length; k++) {
          if (pts[k].y - pts[k - 1].y < GAP) {
            const mid = (pts[k - 1].y + pts[k].y) / 2;
            pts[k - 1].y = Math.max(ca.top + PILL_H / 2 + 2, mid - GAP / 2);
            pts[k].y = Math.min(ca.bottom - PILL_H / 2 - 2, mid + GAP / 2);
            moved = true;
          }
        }
        if (!moved) break;
      }

      ctx.save();
      pts.forEach(({ y, rawVal, user, color }) => {
        const cx = ca.right + AVATAR_R + 4;
        const label = mode === '%'
          ? (rawVal >= 0 ? '+' : '') + rawVal.toFixed(1) + '%'
          : (rawVal >= 0 ? '+$' : '-$') + Math.abs(rawVal).toFixed(0);

        ctx.font = 'bold 13px IBM Plex Mono, monospace';
        const textWidth = ctx.measureText(label).width;
        const textGap = 6;
        const pillLeft = cx - AVATAR_R;
        const pillWidth = AVATAR_R * 2 + textGap + textWidth + PILL_PAD;

        // Pill
        ctx.fillStyle = color;
        roundRectPath(ctx, pillLeft, y - PILL_H / 2, pillWidth, PILL_H, PILL_H / 2);
        ctx.fill();

        // Value text — starts past the avatar's right edge so the avatar
        // (drawn after, on top) doesn't cover the start of the text.
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(label, cx + AVATAR_R + textGap, y);

        // Avatar circle, overlapping the pill's rounded left end
        const img = avatarImages && avatarImages[user.telegram_user_id];
        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, y, AVATAR_R, 0, Math.PI * 2);
        ctx.closePath();
        ctx.clip();
        if (img && img.complete && img.naturalWidth > 0) {
          ctx.drawImage(img, cx - AVATAR_R, y - AVATAR_R, AVATAR_R * 2, AVATAR_R * 2);
        } else {
          ctx.fillStyle = color;
          ctx.fillRect(cx - AVATAR_R, y - AVATAR_R, AVATAR_R * 2, AVATAR_R * 2);
          ctx.fillStyle = '#ffffff';
          ctx.font = 'bold 11px IBM Plex Mono, monospace';
          ctx.textAlign = 'center';
          ctx.fillText(user.initials, cx, y);
        }
        ctx.restore();

        // Ring separating the avatar from the pill/chart background
        ctx.beginPath();
        ctx.arc(cx, y, AVATAR_R, 0, Math.PI * 2);
        ctx.lineWidth = 2;
        ctx.strokeStyle = '#ffffff';
        ctx.stroke();
      });
      ctx.restore();
    },
  };
}
