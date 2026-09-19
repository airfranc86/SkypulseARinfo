const AR_ZONE = 'America/Argentina/Buenos_Aires'

const WEEKDAYS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']
const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

const arDate = new Intl.DateTimeFormat('es-AR', {
  timeZone: AR_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

/** "2026-09-19": el día de `ms` en hora argentina (no el UTC: a las 22:00 ya es "mañana" en UTC). */
export function arDateKey(ms: number): string {
  const parts = arDate.formatToParts(ms)
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}`
}

/** "2026-09-30" + 1 = "2026-10-01". Aritmética de calendario, sin pasar por la zona horaria del navegador. */
export function addDays(date: string, days: number): string {
  const d = new Date(`${date}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

/** "19 sep", "1 oct": día sin cero a la izquierda y mes en tres letras. */
export function formatShortDate(date: string): string {
  const [, month, day] = date.split('-').map(Number)
  return `${day} ${MONTHS[month - 1]}`
}

/** "sáb": el día de la semana en tres letras. Para ejes donde "Mañana" no entra en la banda de una barra. */
export function weekdayShort(date: string): string {
  return WEEKDAYS[new Date(`${date}T12:00:00Z`).getUTCDay()]
}

/**
 * Rótulo de un día: "Hoy", "Mañana" o el día de la semana, siempre con su fecha. Con diez días en
 * pantalla "dom" y "lun" se repiten, y solo el número permite saber cuál es cuál.
 */
export function dayLabel(date: string, todayDate: string): { title: string; date: string } {
  let title: string
  if (date === todayDate) title = 'Hoy'
  else if (date === addDays(todayDate, 1)) title = 'Mañana'
  else title = WEEKDAYS[new Date(`${date}T12:00:00Z`).getUTCDay()]
  return { title, date: formatShortDate(date) }
}
