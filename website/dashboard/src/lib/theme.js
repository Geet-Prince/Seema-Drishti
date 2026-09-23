// Shared severity/color + time helpers kept out of components so files stay
// component-only (fast-refresh friendly).

export const SEV_COLOR = {
  critical: '#ff2d55',
  high: '#ff6b2c',
  medium: '#ffb020',
  low: '#39ff88',
  nominal: '#39ff88',
  informational: '#00f0ff',
};

export const SEV_GLOW = {
  critical: 'rgba(255,45,85,0.55)',
  high: 'rgba(255,107,44,0.5)',
  medium: 'rgba(255,176,32,0.45)',
  low: 'rgba(57,255,136,0.4)',
  nominal: 'rgba(57,255,136,0.4)',
  informational: 'rgba(0,240,255,0.45)',
};

export function relTime(iso) {
  const then = new Date(iso).getTime();
  if (!then) return '';
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
}
