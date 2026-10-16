/** Choosing and writing the forecast hour shown on the pressure map. Pure module: "now" is always a parameter. */

const ZONA = 'America/Argentina/Buenos_Aires'

const PARTES = new Intl.DateTimeFormat('es-AR', {
  weekday: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
  timeZone: ZONA,
})

/** Index of the hour whose valid time is closest to `ahoraMs` (a tie goes to the earlier one); 0 if there is no answer. */
export function indiceDeLaHoraMasCercana(horas: ReadonlyArray<{ valid: string }>, ahoraMs: number): number {
  if (!Number.isFinite(ahoraMs)) return 0
  let mejor = 0
  let distancia = Number.POSITIVE_INFINITY
  horas.forEach((hora, i) => {
    const d = Math.abs(Date.parse(hora.valid) - ahoraMs)
    if (d < distancia) {
      mejor = i
      distancia = d
    }
  })
  return mejor
}

/** A valid time in Argentine time with the weekday: "mié 14 · 21:00 h"; "—" if the date is invalid. */
export function textoDeLaHora(valid: string): string {
  const instante = Date.parse(valid)
  if (!Number.isFinite(instante)) return '—'
  const partes = Object.fromEntries(PARTES.formatToParts(instante).map((p) => [p.type, p.value]))
  const dia = String(partes.weekday).replace(/\.$/, '')
  return `${dia} ${partes.day} · ${partes.hour}:${partes.minute} h`
}
