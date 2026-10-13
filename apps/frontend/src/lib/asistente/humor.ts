/**
 * Mora's mood (the Andean eagle mascot of the assistant). Everything here is pure: plain data in, a mood out,
 * with no React, no DOM and no timers. The clock for the "one change per minute" rule is passed in too.
 *
 * Priority, highest first (the first trigger that holds wins):
 *
 *   alerta > pensando / respondiendo / confundido > dormido > erizado > encogido > planeando > reposo
 *
 * Source: the internal assistant plan (docs/plans/plan-asistente-mascota-2026-10-09.md, addendum A2; docs/ is
 * not versioned). The shared limits are not copied here: the gust limit is `GUST_KMH` from `weatherVerdict.ts`
 * and the warning level is `criticalLevel` from `smnAlertas.ts`. The rain rule is Mora's own (owner decision
 * 2026-10-13): a rain or drizzle icon AND at least `LLUVIA_MINIMA_MM` in the slot, see `llueve`.
 *
 * Bundling note for PR 3: this module imports `smnAlertas.ts` and `weatherVerdict.ts`. The component that uses
 * it must load it lazily (dynamic `import()`) behind `leerConfigAsistente(...).visible`, so none of this ends
 * up in the main chunk while the flag is off.
 */

import type { ConvectiveRisk, SmnAlerta } from '../api.ts'
import { criticalLevel } from '../smnAlertas.ts'
import { GUST_KMH } from '../weatherVerdict.ts'

/**
 * Least precipitation, in millimeters over the current forecast slot, that counts as rain for Mora (owner
 * decision 2026-10-13: 1 mm is not the same as 10 mm). Each slot spans 3 h, so this is millimeters per 3 h, not
 * per hour. It is Mora's own limit: it is deliberately not the 0.1 mm `RAIN_MM` the verdict uses to say "it will
 * rain". Inclusive: exactly 1 mm counts.
 */
export const LLUVIA_MINIMA_MM = 1

/** The moods that only exist while Mora's panel is open (set by the panel, never by the weather). */
export type HumorPanel = 'pensando' | 'respondiendo' | 'confundido'

export type HumorMora = 'alerta' | HumorPanel | 'dormido' | 'erizado' | 'encogido' | 'planeando' | 'reposo'

/** Every mood, in priority order (highest first). The review page walks this list. */
export const HUMORES: readonly HumorMora[] = Object.freeze([
  'alerta',
  'pensando',
  'respondiendo',
  'confundido',
  'dormido',
  'erizado',
  'encogido',
  'planeando',
  'reposo',
] as const)

/**
 * What the mood depends on. The caller (a future component) reads it from `WeatherDashboardResponse` and
 * `useSmnAlertas`. It resolves "the current slot" itself: `riesgoConvectivo` and `precipMm` come from the
 * hourly entry that contains the present time, so this module needs no clock to pick one.
 * A `null` or `undefined` value always means "unknown" and never triggers anything.
 */
export interface DatosHumor {
  /**
   * SMN warnings as `/api/alertas` serves them (the raw list; `criticalLevel` picks orange and red).
   * `null` or `undefined` (not loaded yet, or the feed failed) counts as an empty list.
   */
  readonly alertas: readonly SmnAlerta[] | null | undefined
  /** `convective_risk` of the current hourly slot. */
  readonly riesgoConvectivo: ConvectiveRisk | null | undefined
  /** The panel's phase while it is open and busy; `null` when it is closed or idle. */
  readonly panel: HumorPanel | null
  /** `current.is_day`; `null` when unknown. */
  readonly esDeDia: boolean | null
  /** `current.wind_gust_kmh` (optional in the API); `null` or `undefined` when unknown. */
  readonly rafagaKmh: number | null | undefined
  /** `current.wind_intensity` ("leve", "moderada" or "intensa"); `null` when unknown. */
  readonly intensidadViento: string | null
  /**
   * `current.icon`; `null` when unknown. Mora only counts as raining with a rain or drizzle icon (whole-word
   * match, so `rainbow` does not count) AND enough millimeters in `precipMm`; the icon alone is not enough.
   */
  readonly icono: string | null
  /**
   * `precip_mm` of the current hourly slot, in millimeters over that slot (each forecast slot spans 3 h);
   * `null` or `undefined` when unknown. It only counts together with a rain or drizzle icon, from
   * `LLUVIA_MINIMA_MM` (1 mm, inclusive). `NaN`, infinite and negative values are treated as unknown, which
   * means "not raining".
   */
  readonly precipMm: number | null | undefined
}

/** "rain" or "drizzle" as a whole word of a Meteocons code ("partly-cloudy-day-rain", "overcast-drizzle"). */
const ICONO_LLUVIA = /(?:^|-)(?:rain|drizzle)(?:-|$)/

function hayAlerta(datos: DatosHumor): boolean {
  // ASSUMPTION: the warnings are taken as they come from the feed, with no validity-window filter, exactly
  // like PrevisionClima does with `criticalLevel(alertas)`. Filtering expired ones would need a clock here.
  if (criticalLevel([...(datos.alertas ?? [])]) !== null) return true
  return datos.riesgoConvectivo === 'high' || datos.riesgoConvectivo === 'severe'
}

function hayViento(datos: DatosHumor): boolean {
  // The plan says `>= 40`, so a gust of exactly GUST_KMH counts (owner-confirmed; the hourly strip and the
  // verdict use a strict `>`). ASSUMPTION: "wind_intensity alto" is read as the top tier, "intensa" (60 km/h
  // or more).
  if (typeof datos.rafagaKmh === 'number' && datos.rafagaKmh >= GUST_KMH) return true
  return datos.intensidadViento === 'intensa'
}

/**
 * The one rain predicate. Owner decision 2026-10-13: rain needs BOTH a rain or drizzle icon AND at least
 * `LLUVIA_MINIMA_MM` in the slot. An unknown icon or unknown, NaN, infinite or negative millimeters mean "not
 * raining". `humorDesdeClima` asks it once, for encogido, and only reaches planeando when it is false, so the
 * two moods cannot disagree about whether it is raining.
 */
function llueve(datos: DatosHumor): boolean {
  const hayIconoDeLluvia = typeof datos.icono === 'string' && ICONO_LLUVIA.test(datos.icono)
  const hayAgua = typeof datos.precipMm === 'number' && Number.isFinite(datos.precipMm) && datos.precipMm >= LLUVIA_MINIMA_MM
  return hayIconoDeLluvia && hayAgua
}

function hayTermicas(datos: DatosHumor): boolean {
  // ASSUMPTION: "low or moderate convective risk" must be stated; an unknown risk is not assumed to be low,
  // so without it Mora stays at rest instead of claiming thermals without a storm.
  return datos.esDeDia === true && (datos.riesgoConvectivo === 'low' || datos.riesgoConvectivo === 'moderate')
}

/**
 * Mora's mood for these data. The order of the checks IS the priority list above; being asleep (night) comes
 * after the panel states on purpose, so asking Mora something wakes her up, and after the alert, so a warning
 * wakes her at night.
 *
 * It takes no clock: `esDeDia` already carries day or night, and the caller resolves the current slot.
 */
export function humorDesdeClima(datos: DatosHumor): HumorMora {
  if (hayAlerta(datos)) return 'alerta'
  if (datos.panel) return datos.panel
  if (datos.esDeDia === false) return 'dormido'
  if (hayViento(datos)) return 'erizado'
  if (llueve(datos)) return 'encogido'
  if (hayTermicas(datos)) return 'planeando'
  return 'reposo'
}

/** Minimum time between two mood changes: one minute. */
export const INTERVALO_MINIMO_CAMBIO_MS = 60_000

/** The mood Mora is showing and when it last changed (epoch milliseconds). */
export interface HumorSostenido {
  readonly humor: HumorMora
  readonly cambioEnMs: number
}

const HUMORES_PANEL: ReadonlySet<HumorMora> = new Set<HumorMora>(['pensando', 'respondiendo', 'confundido'])

function esHumorPanel(humor: HumorMora): humor is HumorPanel {
  return HUMORES_PANEL.has(humor)
}

/**
 * Anti-flap rule: Mora never changes between WEATHER moods more than once per minute. Pure: it takes the mood
 * being shown (or `null` the first time), the mood that `humorDesdeClima` now proposes and the current time,
 * and returns the mood to show with the time of its last change. Nothing is mutated; a held mood returns the
 * same object.
 *
 * - First call (`previo` is `null`): the proposed mood is adopted at once and stamped. So do not call it before
 *   the data has arrived: a first call with placeholder data would adopt (and stamp) a mood nobody asked for.
 * - Same mood proposed: nothing changes, the timer is not restarted.
 * - The proposed OR the current mood is a panel mood (pensando, respondiendo, confundido): the change passes at
 *   once and the stamp restarts. The panel reacts to what the user does, so it cannot wait a minute, and when the
 *   panel closes Mora follows the weather immediately instead of staying in respondiendo.
 * - Weather to weather (alerta included): within a minute of the last change the current mood is kept; after a
 *   full minute (60 000 ms or more) it changes and the timer restarts. The first weather change after leaving
 *   the panel therefore waits one minute counted from the moment the weather mood came back.
 *
 * A proposal that was held is not applied later by itself. The caller re-evaluates (calls this again with the
 * mood `humorDesdeClima` proposes at that moment) once the wait is over, one `setTimeout` of
 * `msHastaPoderCambiar(...)`.
 *
 * ASSUMPTION: if the clock went backwards or is not a number, the change goes through, so Mora can never get
 * stuck.
 */
export function sostenerHumor(previo: HumorSostenido | null, propuesto: HumorMora, ahoraMs: number): HumorSostenido {
  if (previo === null) return Object.freeze({ humor: propuesto, cambioEnMs: ahoraMs })
  if (propuesto === previo.humor) return previo
  if (esHumorPanel(propuesto) || esHumorPanel(previo.humor)) return Object.freeze({ humor: propuesto, cambioEnMs: ahoraMs })
  if (msHastaPoderCambiar(previo, ahoraMs) > 0) return previo
  return Object.freeze({ humor: propuesto, cambioEnMs: ahoraMs })
}

/**
 * Milliseconds left until the one-minute window since the last change is over, so the caller can arm ONE
 * `setTimeout` after holding a proposal and then re-evaluate (`humorDesdeClima` and `sostenerHumor` again):
 * `0` when a weather change can go through now, up to `INTERVALO_MINIMO_CAMBIO_MS` right after a change. The
 * result is rounded up to a whole millisecond, so a timer of that length never fires a fraction too early.
 *
 * It only measures the window. It does not look at the moods, so it says nothing about the panel moods, which
 * `sostenerHumor` lets through at any time. It follows the same clock rule: no mood shown yet, a clock that
 * went backwards or a clock that is not a number all mean "no wait" (0).
 */
export function msHastaPoderCambiar(previo: HumorSostenido | null, ahoraMs: number): number {
  if (previo === null) return 0
  const transcurridoMs = ahoraMs - previo.cambioEnMs
  const dentroDeLaVentana = transcurridoMs >= 0 && transcurridoMs < INTERVALO_MINIMO_CAMBIO_MS
  return dentroDeLaVentana ? Math.ceil(INTERVALO_MINIMO_CAMBIO_MS - transcurridoMs) : 0
}
