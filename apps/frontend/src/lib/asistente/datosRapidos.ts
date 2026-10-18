/**
 * What the quick answers (degraded mode) read from what the app already has in React Query's cache: the forecast
 * dashboard, the SMN warnings and the laundry days. Pure: the data and the clock come in, nothing is requested.
 *
 * The verdict is the one the forecast page builds (`buildVerdict`), measured from now. Like Mora's mood, a forecast (or a
 * warnings answer) older than three hours counts as unknown: the quick answers would be telling the weather of another
 * hour. A warnings feed that did not answer is "unknown", never "no warnings": it only leaves the warnings out.
 */
import type { LaundryForecastResponse, SmnAlertasResponse, WeatherDashboardResponse } from '../api.ts'
import { buildVerdict } from '../weatherVerdict.ts'
import { esViejo } from './datosHumor.ts'
import type { DatosRapidos } from './respuestasRapidas.ts'

export function datosRapidosDesde(
  dashboard: WeatherDashboardResponse | null | undefined,
  avisos: SmnAlertasResponse | null | undefined,
  ropa: LaundryForecastResponse | null | undefined,
  ahoraMs: number,
): DatosRapidos {
  const alertas = avisos && avisos.available && !esViejo(avisos.fetched_at, ahoraMs) ? avisos.alertas : []
  const veredicto =
    dashboard && !esViejo(dashboard.fetched_at, ahoraMs)
      ? buildVerdict(
          dashboard.hourly.entries,
          ahoraMs,
          dashboard.rain_today.status_text.toLowerCase().includes('llovizna'),
          alertas,
        )
      : null
  return { veredicto, diasRopa: ropa ? ropa.days : null }
}
