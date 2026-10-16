/**
 * Contract v1 of the pressure-map files (`manifest.json` and one `isobaras_fNNN.json` per forecast
 * hour). The pipeline (`scripts/isobaras/isobaras_core/formato.py`) writes them; this module validates
 * and decodes them. Pure (no React, no `fetch`) so `node --test` can check every rule, and both sides
 * are tested against the same fixture in `tests/fixtures/isobaras/`.
 *
 * Coordinates travel as integers in units of `1 / scale` degrees (0.01° with scale 100). In a line's
 * `c` the first lat,lon pair is absolute and the following ones are differences from the previous
 * point. A `closed` line does not repeat its first point: the client closes it when drawing.
 *
 * The files come from a third-party host (GitHub Pages), so nothing is trusted: anything that does not
 * match the contract is rejected with a reason instead of being drawn.
 */

export interface Punto {
  readonly lat: number
  readonly lon: number
}

export interface Bbox {
  readonly lonMin: number
  readonly latMin: number
  readonly lonMax: number
  readonly latMax: number
}

export interface HoraDelManifest {
  /** Forecast hour (hours after the cycle). */
  readonly f: number
  /** Valid time, `AAAA-MM-DDTHH:MMZ`. */
  readonly valid: string
  readonly file: string
}

export interface Manifest {
  readonly v: 1
  readonly source: string
  /** Model cycle, `AAAA-MM-DDTHH:MMZ`. */
  readonly cycle: string
  readonly generated: string
  readonly bbox: Bbox
  readonly intervalHpa: number
  readonly scale: number
  readonly hours: ReadonlyArray<HoraDelManifest>
}

export interface Linea {
  readonly p: number
  readonly cerrada: boolean
  /** Absolute points in degrees. A closed line does not repeat the first one. */
  readonly puntos: ReadonlyArray<Punto>
  readonly etiquetas: ReadonlyArray<Punto>
}

export interface Centro {
  readonly t: 'H' | 'L'
  readonly p: number
  readonly lat: number
  readonly lon: number
}

export interface Hora {
  readonly cycle: string
  readonly f: number
  readonly valid: string
  readonly lineas: ReadonlyArray<Linea>
  readonly centros: ReadonlyArray<Centro>
}

export type MotivoRechazo = 'version' | 'formato' | 'fuera-de-bbox' | 'ciclo-cambiado'

export type Resultado<T> =
  | { readonly ok: true; readonly valor: T }
  | { readonly ok: false; readonly motivo: MotivoRechazo; readonly detalle: string }

// Same rules as the Python reader (`formato.py`); the shared cases in `tests/fixtures/isobaras/rechazos.json` keep them equal.
const FECHA = /^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z$/
const ARCHIVO_HORA = /^isobaras_f[0-9]{3}\.json$/

// The files come from a third-party host: bound everything before drawing it.
const MAX_ABS = 2 ** 31
const MAX_BBOX_ABS = 360
const MAX_HORAS = 129
const MAX_LINEAS = 200
const MAX_PUNTOS_POR_LINEA = 5000
const MAX_ETIQUETAS_POR_LINEA = 2
const MAX_CENTROS = 30

class Rechazo extends Error {
  readonly motivo: MotivoRechazo

  constructor(motivo: MotivoRechazo, detalle: string) {
    super(detalle)
    this.motivo = motivo
  }
}

const rechazar = (motivo: MotivoRechazo, detalle: string): never => {
  throw new Rechazo(motivo, detalle)
}

function comoResultado<T>(leer: () => T): Resultado<T> {
  try {
    return { ok: true, valor: leer() }
  } catch (e) {
    if (e instanceof Rechazo) return { ok: false, motivo: e.motivo, detalle: e.message }
    throw e
  }
}

const esObjeto = (x: unknown): x is Record<string, unknown> => typeof x === 'object' && x !== null && !Array.isArray(x)
const esEntero = (x: unknown): x is number => typeof x === 'number' && Number.isInteger(x) && Math.abs(x) <= MAX_ABS
/** A real calendar minute: `Date` rolls "02-31" over to March, so the date must survive a round trip. */
const esFecha = (x: unknown): x is string =>
  typeof x === 'string' && FECHA.test(x) && Number.isFinite(Date.parse(x)) && new Date(x).toISOString().slice(0, 16) + 'Z' === x

function objeto(x: unknown, donde: string): Record<string, unknown> {
  return esObjeto(x) ? x : rechazar('formato', `${donde}: se esperaba un objeto`)
}

function entero(x: unknown, donde: string): number {
  return esEntero(x) ? x : rechazar('formato', `${donde}: se esperaba un entero`)
}

function fecha(x: unknown, donde: string): string {
  return esFecha(x) ? x : rechazar('formato', `${donde}: se esperaba AAAA-MM-DDTHH:MMZ`)
}

function lista(x: unknown, donde: string, maximo?: number): unknown[] {
  if (!Array.isArray(x)) return rechazar('formato', `${donde}: se esperaba una lista`)
  if (maximo !== undefined && x.length > maximo) rechazar('formato', `${donde}: más de ${maximo} elementos`)
  return x
}

function version(raw: Record<string, unknown>): void {
  const v = entero(raw.v, 'v')
  if (v !== 1) rechazar('version', `versión ${v} desconocida`)
}

/** Validates and decodes `manifest.json`. */
export function leerManifest(raw: unknown): Resultado<Manifest> {
  return comoResultado(() => {
    const m = objeto(raw, 'manifest')
    version(m)
    const caja = lista(m.bbox, 'bbox')
    if (caja.length !== 4 || !caja.every((n) => typeof n === 'number' && Math.abs(n) <= MAX_BBOX_ABS)) {
      rechazar('formato', 'bbox: se esperaban 4 números')
    }
    const [lonMin, latMin, lonMax, latMax] = caja as number[]
    if (lonMin >= lonMax || latMin >= latMax) rechazar('formato', 'bbox: mínimos mayores que máximos')
    const intervalHpa = entero(m.interval_hpa, 'interval_hpa')
    const scale = entero(m.scale, 'scale')
    if (intervalHpa <= 0 || scale <= 0) rechazar('formato', 'interval_hpa y scale tienen que ser positivos')
    if (typeof m.source !== 'string') rechazar('formato', 'source: se esperaba texto')
    const hours = lista(m.hours, 'hours', MAX_HORAS).map((h, i): HoraDelManifest => {
      const hora = objeto(h, `hours[${i}]`)
      const f = entero(hora.f, `hours[${i}].f`)
      if (f < 0) rechazar('formato', `hours[${i}].f: no puede ser negativo`)
      const file = hora.file
      if (typeof file !== 'string' || !ARCHIVO_HORA.test(file)) {
        rechazar('formato', `hours[${i}].file: nombre de archivo no permitido`)
      }
      return { f, valid: fecha(hora.valid, `hours[${i}].valid`), file: file as string }
    })
    if (hours.length === 0) rechazar('formato', 'hours: no puede estar vacía')
    for (let i = 1; i < hours.length; i += 1) {
      if (hours[i].f <= hours[i - 1].f) rechazar('formato', 'hours: las horas tienen que ir en orden creciente')
    }
    return {
      v: 1,
      source: m.source as string,
      cycle: fecha(m.cycle, 'cycle'),
      generated: fecha(m.generated, 'generated'),
      bbox: { lonMin, latMin, lonMax, latMax },
      intervalHpa,
      scale,
      hours,
    }
  })
}

function dentro(punto: Punto, bbox: Bbox): boolean {
  return punto.lat >= bbox.latMin && punto.lat <= bbox.latMax && punto.lon >= bbox.lonMin && punto.lon <= bbox.lonMax
}

function enBbox(punto: Punto, bbox: Bbox, donde: string): Punto {
  if (!dentro(punto, bbox)) rechazar('fuera-de-bbox', `${donde}: fuera del recorte del manifest`)
  return punto
}

/**
 * Validates and decodes one hour file against its manifest. Rejects a different `scale`, an unknown
 * version, a malformed body, any point outside the manifest's `bbox`, and a file whose `cycle` is not
 * the manifest's (`ciclo-cambiado`: a new cycle was published between the two requests).
 */
export function leerHora(raw: unknown, manifest: Manifest): Resultado<Hora> {
  return comoResultado(() => {
    const h = objeto(raw, 'hora')
    version(h)
    if (entero(h.scale, 'scale') !== manifest.scale) rechazar('formato', 'scale: distinta de la del manifest')
    const cycle = fecha(h.cycle, 'cycle')
    if (cycle !== manifest.cycle) rechazar('ciclo-cambiado', 'el ciclo de la hora no es el del manifest')
    const grado = (n: number) => n / manifest.scale
    const f = entero(h.f, 'f')
    const valid = fecha(h.valid, 'valid')
    const delManifest = manifest.hours.find((x) => x.f === f)
    if (!delManifest || delManifest.valid !== valid) rechazar('formato', 'f/valid: la hora no coincide con la del manifest')

    const lineas = lista(h.lines, 'lines', MAX_LINEAS).map((l, i): Linea => {
      const linea = objeto(l, `lines[${i}]`)
      const p = entero(linea.p, `lines[${i}].p`)
      const cerrada = linea.closed
      if (typeof cerrada !== 'boolean') return rechazar('formato', `lines[${i}].closed: se esperaba true o false`)
      const c = lista(linea.c, `lines[${i}].c`, 2 * MAX_PUNTOS_POR_LINEA)
      if (c.length % 2 !== 0 || c.length < 4) rechazar('formato', `lines[${i}].c: se esperaban pares lat,lon (al menos 2)`)
      const puntos: Punto[] = []
      let lat = 0
      let lon = 0
      for (let k = 0; k < c.length; k += 2) {
        const dLat = entero(c[k], `lines[${i}].c[${k}]`)
        const dLon = entero(c[k + 1], `lines[${i}].c[${k + 1}]`)
        lat = k === 0 ? dLat : lat + dLat
        lon = k === 0 ? dLon : lon + dLon
        puntos.push(enBbox({ lat: grado(lat), lon: grado(lon) }, manifest.bbox, `lines[${i}].c[${k}]`))
      }
      const primero = puntos[0]
      const ultimo = puntos[puntos.length - 1]
      if (cerrada && (puntos.length < 3 || (ultimo.lat === primero.lat && ultimo.lon === primero.lon))) {
        rechazar('formato', `lines[${i}]: una curva cerrada necesita 3 puntos y no repite el primero`)
      }
      const etiquetas = lista(linea.labels, `lines[${i}].labels`, MAX_ETIQUETAS_POR_LINEA).map((e, j) => {
        const par = lista(e, `lines[${i}].labels[${j}]`)
        if (par.length !== 2) rechazar('formato', `lines[${i}].labels[${j}]: se esperaba [lat, lon]`)
        const punto = { lat: grado(entero(par[0], 'label lat')), lon: grado(entero(par[1], 'label lon')) }
        return enBbox(punto, manifest.bbox, `lines[${i}].labels[${j}]`)
      })
      return { p, cerrada, puntos, etiquetas }
    })

    const centros = lista(h.centers, 'centers', MAX_CENTROS).map((c, i): Centro => {
      const centro = objeto(c, `centers[${i}]`)
      if (centro.t !== 'H' && centro.t !== 'L') rechazar('formato', `centers[${i}].t: se esperaba H o L`)
      const punto = {
        lat: grado(entero(centro.lat, `centers[${i}].lat`)),
        lon: grado(entero(centro.lon, `centers[${i}].lon`)),
      }
      enBbox(punto, manifest.bbox, `centers[${i}]`)
      return { t: centro.t as 'H' | 'L', p: entero(centro.p, `centers[${i}].p`), ...punto }
    })

    return { cycle, f, valid, lineas, centros }
  })
}

/** Points to draw a line: a closed one gets its first point appended; an open one is returned as is. */
export function puntosParaDibujar(linea: Linea): ReadonlyArray<Punto> {
  return linea.cerrada && linea.puntos.length > 0 ? [...linea.puntos, linea.puntos[0]] : linea.puntos
}
