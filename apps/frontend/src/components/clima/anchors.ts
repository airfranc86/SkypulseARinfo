/** Anclas del detalle de la previsión: hacia acá lleva un día de "Próximos días". */

/** La tira de horas (HourlyStrip). */
export const HOURLY_ANCHOR_ID = 'prevision-hourly'

/** La fila de un día en el pronóstico de 7 días (Forecast7dList), para los días que no tienen horas. */
export function dayRowId(date: string): string {
  return `dia-${date}`
}
