export interface MagnitudeInfo {
  textColor: string
  fontWeight: number
  dotColor: string
  rowBg: string
  fontSize: string
  glow: boolean
}

export function magnitudeInfo(mag: number): MagnitudeInfo {
  if (mag >= 6)   return { textColor: '#ff6b6b', fontWeight: 800, dotColor: '#ff3333', rowBg: 'rgba(224,85,69,0.11)', fontSize: '1.35rem', glow: true }
  if (mag >= 4.5) return { textColor: '#e05545', fontWeight: 700, dotColor: '#e05545', rowBg: 'rgba(224,85,69,0.07)', fontSize: '1.15rem', glow: true }
  if (mag >= 4)   return { textColor: '#f0a030', fontWeight: 600, dotColor: '#f0a030', rowBg: 'rgba(240,160,48,0.05)', fontSize: '1.05rem', glow: false }
  if (mag >= 3)   return { textColor: '#c8a84b', fontWeight: 500, dotColor: '#c8a84b', rowBg: 'transparent',         fontSize: '0.9rem',  glow: false }
  return               { textColor: 'var(--color-muted-foreground)', fontWeight: 400, dotColor: '#5aaad8', rowBg: 'transparent', fontSize: '0.875rem', glow: false }
}
