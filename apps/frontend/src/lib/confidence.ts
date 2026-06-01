export const CONFIDENCE_COLORS: Record<string, string> = {
  alta:  '#3ecf7a',
  media: '#f0a030',
  baja:  '#e05545',
}

export function confidenceColor(label: string | undefined): string {
  return CONFIDENCE_COLORS[(label ?? '').toLowerCase()] ?? '#888888'
}
