// Live-refresh device online status on the dashboard.
async function refresh() {
  try {
    const base = window.PORTAL_BASE || '';
    const res = await fetch(base + '/api/status', { credentials: 'same-origin' });
    if (!res.ok) return;
    const data = await res.json();
    for (const d of data.devices) {
      const row = document.querySelector(`tr[data-device="${d.id}"]`);
      if (!row) continue;
      const dot = row.querySelector('[data-role="dot"]');
      const label = row.querySelector('[data-role="status"]');
      if (dot) dot.className = 'dot ' + (d.online ? 'on' : 'off');
      if (label) label.textContent = d.online ? 'online' : 'offline';
    }
  } catch (e) { /* ignore transient errors */ }
}
setInterval(refresh, 10000);
