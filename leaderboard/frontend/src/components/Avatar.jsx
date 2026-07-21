import { useState } from 'react';

/** Circular avatar — photo if available, else colored initials. */
export default function Avatar({ user, className, borderWidth = 1.5 }) {
  const [imgFailed, setImgFailed] = useState(false);
  const border = `${borderWidth}px solid ${user.color}`;

  if (!user.photo_url || imgFailed) {
    return (
      <div className={`avatar ${className}`} style={{ background: user.color, color: '#fff' }}>
        {user.initials}
      </div>
    );
  }
  return (
    <div
      className={`avatar ${className}`}
      style={{ border, overflow: 'hidden', padding: 0, background: `${user.color}22` }}
    >
      <img
        src={user.photo_url}
        alt=""
        style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        onError={() => setImgFailed(true)}
      />
    </div>
  );
}
