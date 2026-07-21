export async function fetchLeaderboard() {
  const res = await fetch('/leaderboard/data/leaderboard');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
