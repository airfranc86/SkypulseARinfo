import { useState, useRef, useEffect, useCallback } from 'react'
import { FadeContent } from '@/components/animated/FadeContent'
import { Dither } from '@/components/animated/Dither'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MetarData {
  icao?: string
  raw_text?: string
  flight_category?: string
  station?: { name?: string }
  wind?: {
    degrees?: number
    direction?: string
    speed_kts?: number
    gust_kts?: number
    speed?: number
  }
  visibility?: {
    meters_float?: number
    meters?: number
    miles_float?: number
    text?: string
  }
  clouds?: Array<{ code?: string; base_feet_agl?: number; type?: string }>
  temperature?: { celsius?: number; value?: number }
  dewpoint?: { celsius?: number; value?: number }
  barometer?: { hpa?: number }
  observed?: string
}

interface IcaoEntry {
  code: string
  city: string
  country: string
  region: string
  full: string
}

// ---------------------------------------------------------------------------
// ICAO database
// ---------------------------------------------------------------------------

const ICAO_DB: IcaoEntry[] = [
  // ARGENTINA
  { code:'SAEZ', city:'Buenos Aires',          country:'Argentina',        region:'AR', full:'Ezeiza Int\'l' },
  { code:'SABE', city:'Buenos Aires',          country:'Argentina',        region:'AR', full:'Aeroparque Jorge Newbery' },
  { code:'SACO', city:'Córdoba',               country:'Argentina',        region:'AR', full:'Aeropuerto Córdoba' },
  { code:'SAME', city:'Mendoza',               country:'Argentina',        region:'AR', full:'El Plumerillo' },
  { code:'SARS', city:'Rosario',               country:'Argentina',        region:'AR', full:'Islas Malvinas' },
  { code:'SANT', city:'Tucumán',               country:'Argentina',        region:'AR', full:'Teniente Benjamín Matienzo' },
  { code:'SASA', city:'Salta',                 country:'Argentina',        region:'AR', full:'Martín Miguel de Güemes' },
  { code:'SASJ', city:'San Juan',              country:'Argentina',        region:'AR', full:'Domingo Faustino Sarmiento' },
  { code:'SAVB', city:'Bariloche',             country:'Argentina',        region:'AR', full:'Teniente Luis Candelaria' },
  { code:'SAWC', city:'Comodoro Rivadavia',    country:'Argentina',        region:'AR', full:'General Enrique Mosconi' },
  { code:'SAWG', city:'Río Gallegos',          country:'Argentina',        region:'AR', full:'Piloto Civil N. Fernández' },
  { code:'SAWO', city:'Neuquén',               country:'Argentina',        region:'AR', full:'Presidente Perón' },
  { code:'SAWH', city:'Ushuaia',               country:'Argentina',        region:'AR', full:'Malvinas Argentinas' },
  { code:'SAZR', city:'Santa Rosa',            country:'Argentina',        region:'AR', full:'Aeropuerto Santa Rosa' },
  { code:'SAVV', city:'Viedma',                country:'Argentina',        region:'AR', full:'Gobernador Edgardo Castello' },
  { code:'SAAC', city:'Concordia',             country:'Argentina',        region:'AR', full:'Aeropuerto Concordia' },
  { code:'SAAI', city:'Mar del Plata',         country:'Argentina',        region:'AR', full:'Ástor Piazzolla' },
  { code:'SADP', city:'Posadas',               country:'Argentina',        region:'AR', full:'Libertador General San Martín' },
  { code:'SATK', city:'Catamarca',             country:'Argentina',        region:'AR', full:'Coronel Felipe Varela' },
  { code:'SANL', city:'La Rioja',              country:'Argentina',        region:'AR', full:'Aeropuerto La Rioja' },
  // ESTADOS UNIDOS
  { code:'KJFK', city:'Nueva York',            country:'Estados Unidos',   region:'US', full:'John F. Kennedy Int\'l' },
  { code:'KLGA', city:'Nueva York',            country:'Estados Unidos',   region:'US', full:'LaGuardia' },
  { code:'KEWR', city:'Newark',                country:'Estados Unidos',   region:'US', full:'Newark Liberty Int\'l' },
  { code:'KORD', city:'Chicago',               country:'Estados Unidos',   region:'US', full:'O\'Hare Int\'l' },
  { code:'KLAX', city:'Los Ángeles',           country:'Estados Unidos',   region:'US', full:'Los Angeles Int\'l' },
  { code:'KSFO', city:'San Francisco',         country:'Estados Unidos',   region:'US', full:'San Francisco Int\'l' },
  { code:'KMIA', city:'Miami',                 country:'Estados Unidos',   region:'US', full:'Miami Int\'l' },
  { code:'KATL', city:'Atlanta',               country:'Estados Unidos',   region:'US', full:'Hartsfield-Jackson Atlanta' },
  { code:'KDFW', city:'Dallas',                country:'Estados Unidos',   region:'US', full:'Dallas/Fort Worth Int\'l' },
  { code:'KDEN', city:'Denver',                country:'Estados Unidos',   region:'US', full:'Denver Int\'l' },
  { code:'KLAS', city:'Las Vegas',             country:'Estados Unidos',   region:'US', full:'Harry Reid Int\'l' },
  { code:'KPHX', city:'Phoenix',               country:'Estados Unidos',   region:'US', full:'Phoenix Sky Harbor' },
  { code:'KSEA', city:'Seattle',               country:'Estados Unidos',   region:'US', full:'Seattle-Tacoma Int\'l' },
  { code:'KBOS', city:'Boston',                country:'Estados Unidos',   region:'US', full:'Logan Int\'l' },
  { code:'KIAD', city:'Washington D.C.',        country:'Estados Unidos',   region:'US', full:'Dulles Int\'l' },
  { code:'KMCO', city:'Orlando',               country:'Estados Unidos',   region:'US', full:'Orlando Int\'l' },
  { code:'KIAH', city:'Houston',               country:'Estados Unidos',   region:'US', full:'George Bush Intercontinental' },
  { code:'PHNL', city:'Honolulu',              country:'Estados Unidos',   region:'US', full:'Daniel K. Inouye Int\'l' },
  { code:'PANC', city:'Anchorage',             country:'Estados Unidos',   region:'US', full:'Ted Stevens Anchorage Int\'l' },
  // EUROPA
  { code:'EGLL', city:'Londres',               country:'Reino Unido',      region:'EU', full:'Heathrow' },
  { code:'LFPG', city:'París',                 country:'Francia',          region:'EU', full:'Charles de Gaulle' },
  { code:'EDDF', city:'Fráncfort',             country:'Alemania',         region:'EU', full:'Frankfurt am Main' },
  { code:'LEMD', city:'Madrid',                country:'España',           region:'EU', full:'Adolfo Suárez Barajas' },
  { code:'LIRF', city:'Roma',                  country:'Italia',           region:'EU', full:'Fiumicino Leonardo da Vinci' },
  { code:'EHAM', city:'Ámsterdam',             country:'Países Bajos',     region:'EU', full:'Schiphol' },
  { code:'LOWW', city:'Viena',                 country:'Austria',          region:'EU', full:'Vienna Int\'l' },
  { code:'LSZH', city:'Zúrich',               country:'Suiza',            region:'EU', full:'Kloten' },
  { code:'LKPR', city:'Praga',                 country:'Rep. Checa',       region:'EU', full:'Václav Havel' },
  { code:'EPWA', city:'Varsovia',              country:'Polonia',          region:'EU', full:'Chopin' },
  { code:'EFHK', city:'Helsinki',              country:'Finlandia',        region:'EU', full:'Helsinki-Vantaa' },
  { code:'EKCH', city:'Copenhague',            country:'Dinamarca',        region:'EU', full:'Kastrup' },
  { code:'ESSA', city:'Estocolmo',             country:'Suecia',           region:'EU', full:'Arlanda' },
  { code:'EBBR', city:'Bruselas',              country:'Bélgica',          region:'EU', full:'Brussels Airport' },
  { code:'LPPT', city:'Lisboa',                country:'Portugal',         region:'EU', full:'Humberto Delgado' },
  { code:'LGAV', city:'Atenas',                country:'Grecia',           region:'EU', full:'Eleftherios Venizelos' },
  { code:'EIDW', city:'Dublín',               country:'Irlanda',          region:'EU', full:'Dublin Airport' },
  { code:'UUEE', city:'Moscú',                country:'Rusia',            region:'EU', full:'Sheremetyevo' },
  // URUGUAY
  { code:'SUMU', city:'Montevideo',            country:'Uruguay',          region:'UY', full:'Carrasco Int\'l' },
  { code:'SUPU', city:'Punta del Este',        country:'Uruguay',          region:'UY', full:'C. A. Curbelo Int\'l' },
  { code:'SURV', city:'Rivera',                country:'Uruguay',          region:'UY', full:'Aeropuerto Rivera' },
  { code:'SULS', city:'Salto',                 country:'Uruguay',          region:'UY', full:'Aeropuerto Salto' },
  // BRASIL
  { code:'SBGR', city:'São Paulo',             country:'Brasil',           region:'BR', full:'Guarulhos Int\'l' },
  { code:'SBSP', city:'São Paulo',             country:'Brasil',           region:'BR', full:'Congonhas' },
  { code:'SBGL', city:'Río de Janeiro',        country:'Brasil',           region:'BR', full:'Galeão Int\'l' },
  { code:'SBBR', city:'Brasilia',              country:'Brasil',           region:'BR', full:'Presidente Juscelino Kubitschek' },
  { code:'SBSV', city:'Salvador',              country:'Brasil',           region:'BR', full:'Deputado Luís Eduardo Magalhães' },
  { code:'SBMN', city:'Manaos',                country:'Brasil',           region:'BR', full:'Eduardo Gomes Int\'l' },
  { code:'SBPO', city:'Porto Alegre',          country:'Brasil',           region:'BR', full:'Salgado Filho Int\'l' },
  { code:'SBCT', city:'Curitiba',              country:'Brasil',           region:'BR', full:'Afonso Pena Int\'l' },
  { code:'SBRF', city:'Recife',                country:'Brasil',           region:'BR', full:'Guararapes Int\'l' },
  // CHILE
  { code:'SCEL', city:'Santiago',              country:'Chile',            region:'CL', full:'Arturo Merino Benítez' },
  { code:'SCFA', city:'Antofagasta',           country:'Chile',            region:'CL', full:'Cerro Moreno' },
  { code:'SCIE', city:'Concepción',            country:'Chile',            region:'CL', full:'Carriel Sur' },
  { code:'SCTE', city:'Puerto Montt',          country:'Chile',            region:'CL', full:'El Tepual' },
  { code:'SCAR', city:'Arica',                 country:'Chile',            region:'CL', full:'Chacalluta' },
  { code:'SCIP', city:'Isla de Pascua',        country:'Chile',            region:'CL', full:'Mataveri Int\'l' },
  { code:'SCDA', city:'Iquique',               country:'Chile',            region:'CL', full:'Diego Aracena Int\'l' },
  // PERÚ
  { code:'SPJC', city:'Lima',                  country:'Perú',             region:'PE', full:'Jorge Chávez Int\'l' },
  { code:'SPQU', city:'Arequipa',              country:'Perú',             region:'PE', full:'Rodríguez Ballón Int\'l' },
  { code:'SPZO', city:'Cusco',                 country:'Perú',             region:'PE', full:'Alejandro Velasco Astete Int\'l' },
  // ECUADOR
  { code:'SEQM', city:'Quito',                 country:'Ecuador',          region:'EC', full:'Mariscal Sucre Int\'l' },
  { code:'SEGU', city:'Guayaquil',             country:'Ecuador',          region:'EC', full:'José Joaquín de Olmedo Int\'l' },
  // COLOMBIA
  { code:'SKBO', city:'Bogotá',               country:'Colombia',         region:'CO', full:'El Dorado Int\'l' },
  { code:'SKMD', city:'Medellín',              country:'Colombia',         region:'CO', full:'Olaya Herrera' },
  { code:'SKCL', city:'Cali',                  country:'Colombia',         region:'CO', full:'Alfonso Bonilla Aragón' },
  { code:'SKBQ', city:'Barranquilla',          country:'Colombia',         region:'CO', full:'Ernesto Cortissoz Int\'l' },
  // REP. DOMINICANA
  { code:'MDSD', city:'Santo Domingo',         country:'Rep. Dominicana',  region:'DO', full:'Las Américas Int\'l' },
  { code:'MDPP', city:'Puerto Plata',          country:'Rep. Dominicana',  region:'DO', full:'Gregorio Luperón Int\'l' },
  { code:'MDPC', city:'Punta Cana',            country:'Rep. Dominicana',  region:'DO', full:'Punta Cana Int\'l' },
]

const REGIONS = [
  { id: 'all', label: 'Todo' },
  { id: 'AR',  label: '🇦🇷 Argentina' },
  { id: 'US',  label: '🇺🇸 EE.UU.' },
  { id: 'EU',  label: '🇪🇺 Europa' },
  { id: 'UY',  label: '🇺🇾 Uruguay' },
  { id: 'BR',  label: '🇧🇷 Brasil' },
  { id: 'CL',  label: '🇨🇱 Chile' },
  { id: 'PE',  label: '🇵🇪 Perú' },
  { id: 'EC',  label: '🇪🇨 Ecuador' },
  { id: 'CO',  label: '🇨🇴 Colombia' },
  { id: 'DO',  label: '🇩🇴 R. Dominicana' },
]

// ---------------------------------------------------------------------------
// Flight category helpers
// ---------------------------------------------------------------------------

const CAT_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  VFR:     { color: '#3ecf7a', bg: 'rgba(62,207,122,.12)',  border: 'rgba(62,207,122,.4)'  },
  MVFR:    { color: '#5aaad8', bg: 'rgba(43,143,212,.12)',  border: 'rgba(43,143,212,.4)'  },
  IFR:     { color: '#e05545', bg: 'rgba(192,57,43,.12)',   border: 'rgba(192,57,43,.4)'   },
  LIFR:    { color: '#cc66ff', bg: 'rgba(204,102,255,.12)', border: 'rgba(204,102,255,.4)' },
  UNKNOWN: { color: '#90aabb', bg: 'rgba(96,112,128,.12)',  border: 'rgba(96,112,128,.4)'  },
}

function FlightCatBadge({ cat }: { cat: string }) {
  const s = CAT_STYLES[cat] ?? CAT_STYLES.UNKNOWN
  return (
    <span
      className="px-3 py-1.5 rounded text-[.75rem] font-medium tracking-wide"
      style={{ color: s.color, background: s.bg, border: `1px solid ${s.border}` }}
    >
      {cat}
    </span>
  )
}

// ---------------------------------------------------------------------------
// METAR raw annotated (colored tokens)
// ---------------------------------------------------------------------------

type Token = { text: string; color?: string }

function MetarRaw({ tokens, size = 'base' }: { tokens: Token[]; size?: 'base' | 'sm' }) {
  return (
    <div
      className={`rounded-md px-5 py-4 overflow-x-auto whitespace-pre-wrap break-all leading-[1.8] ${size === 'sm' ? 'text-[.78rem]' : 'text-[.82rem]'}`}
      style={{
        fontFamily: '"JetBrains Mono", "Fira Code", monospace',
        color: '#c8e6ff',
        background: '#020810',
        border: '1px solid var(--color-border)',
      }}
    >
      {tokens.map((t, i) =>
        t.color ? <span key={i} style={{ color: t.color }}>{t.text}</span> : t.text
      )}
    </div>
  )
}

// Colors
const C = {
  station: '#c8a84b',
  time:    '#90aabb',
  wind:    '#f0a030',
  vis:     '#5aaad8',
  cloud:   '#3ecf7a',
  temp:    '#ff9966',
  qnh:     '#bb88ff',
  phenom:  '#ff6b6b',
}

// ---------------------------------------------------------------------------
// FieldCard
// ---------------------------------------------------------------------------

function FieldCard({
  label,
  color,
  value,
  note,
}: {
  label: string
  color: string
  value: string
  note: string
}) {
  return (
    <div
      className="rounded-md p-4 transition-colors"
      style={{
        background: 'var(--color-card)',
        border: '1px solid var(--color-border)',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(42,74,112,.8)' }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-border)' }}
    >
      <div className="text-[.63rem] font-medium tracking-widest uppercase mb-1" style={{ color }}>
        {label}
      </div>
      <div className="text-[.85rem] mb-1.5" style={{ fontFamily: 'monospace', color }}>
        {value}
      </div>
      <p className="text-[.78rem] leading-[1.65]" style={{ color: 'var(--color-muted-foreground)' }}>
        {note}
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Visibility / cloud helpers
// ---------------------------------------------------------------------------

function visNote(m: number | null): string {
  if (m === null) return ''
  if (m >= 9999) return 'Excelente visibilidad — VFR sin restricciones'
  if (m >= 5000) return 'Buena visibilidad — VFR posible'
  if (m >= 3000) return 'Visibilidad reducida — MVFR'
  if (m >= 1600) return 'Visibilidad baja — condiciones IFR'
  return 'Visibilidad muy baja — LIFR, condiciones críticas'
}

function cloudNote(clouds: MetarData['clouds']): string {
  if (!clouds || clouds.length === 0) return ''
  const hasCB = clouds.some(c => c.type === 'CB')
  const lowestBKN = clouds.find(c => c.code === 'BKN' || c.code === 'OVC')
  if (hasCB) return '⚠️ Cumulonimbus reportado — condición crítica'
  if (lowestBKN) return `Techo definido a ${lowestBKN.base_feet_agl} ft AGL`
  return 'Sin capa de techo definida'
}

// ---------------------------------------------------------------------------
// METAR result display
// ---------------------------------------------------------------------------

function MetarResult({ metar, taf }: { metar: MetarData; taf: string | null }) {
  const windData = metar.wind
  const windVal = windData
    ? `${windData.degrees ?? windData.direction ?? 'VRB'}° / ${windData.speed_kts ?? windData.speed ?? '?'} kt${windData.gust_kts ? ` G${windData.gust_kts}` : ''}`
    : null
  const windNote = windData?.gust_kts
    ? `Ráfagas de ${windData.gust_kts} kt — atención al despegue y aterrizaje`
    : 'Sin ráfagas reportadas'

  const visData = metar.visibility
  const visM = visData
    ? (visData.meters_float ?? visData.meters ?? (visData.miles_float != null ? Math.round(visData.miles_float * 1609) : null))
    : null
  const visDisplay = visM === null
    ? (visData?.text ?? 'N/D')
    : visM >= 9999 ? '≥ 10 km' : `${visM} m`

  const tempC = metar.temperature?.celsius ?? metar.temperature?.value
  const dewC  = metar.dewpoint?.celsius ?? metar.dewpoint?.value
  const diff  = typeof tempC === 'number' && typeof dewC === 'number' ? Math.abs(tempC - dewC) : null
  const qnhHpa = metar.barometer?.hpa

  return (
    <div className="space-y-4">
      {/* Station + category */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div
            className="text-2xl font-normal"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            {metar.icao}
          </div>
          <div className="text-[.75rem] mt-0.5" style={{ color: 'var(--color-muted-foreground)' }}>
            {metar.station?.name}
          </div>
        </div>
        {metar.flight_category && <FlightCatBadge cat={metar.flight_category} />}
      </div>

      {/* Hero callout — IFR / LIFR */}
      {(metar.flight_category === 'IFR' || metar.flight_category === 'LIFR') && (() => {
        const isLIFR = metar.flight_category === 'LIFR'
        const color = isLIFR ? '#cc66ff' : 'var(--color-warn)'
        const colorSoft = isLIFR ? 'rgba(204,102,255,.8)' : 'var(--color-crit-soft)'
        const bg = isLIFR ? 'rgba(204,102,255,.06)' : 'rgba(224,85,69,.06)'
        const border = isLIFR ? 'rgba(204,102,255,.25)' : 'rgba(224,85,69,.25)'
        const msg = isLIFR
          ? 'Visibilidad extremadamente reducida — condición LIFR activa. Operaciones VFR prohibidas.'
          : 'Condición IFR activa — techo bajo o visibilidad reducida. Verificar NOTAMs antes de operar.'
        return (
          <div
            className="flex items-center gap-3 rounded-xl px-5 py-4"
            style={{ background: bg, border: `1px solid ${border}` }}
          >
            <span className="relative flex size-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: color }} />
              <span className="relative inline-flex size-2 rounded-full" style={{ background: color }} />
            </span>
            <span className="text-[.8rem] font-medium" style={{ color: colorSoft }}>
              {msg}
            </span>
          </div>
        )
      })()}

      {/* Raw */}
      <div>
        <p className="text-[.67rem] font-medium tracking-widest uppercase mb-1.5" style={{ color: 'var(--color-muted-foreground)', opacity: 0.5 }}>
          Reporte raw
        </p>
        <div
          className="rounded-md px-5 py-4 overflow-x-auto text-[.82rem] leading-[1.8]"
          style={{ fontFamily: 'monospace', color: '#c8e6ff', background: '#020810', border: '1px solid var(--color-border)' }}
        >
          {metar.raw_text}
        </div>
      </div>

      {/* Fields */}
      <div>
        <p className="text-[.67rem] font-medium tracking-widest uppercase mb-2" style={{ color: 'var(--color-muted-foreground)', opacity: 0.5 }}>
          Desglose
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {windVal && <FieldCard label="Viento" color="#f0a030" value={windVal} note={windNote} />}
          {visData && <FieldCard label="Visibilidad" color="#5aaad8" value={visDisplay} note={visNote(visM)} />}
          {metar.clouds && metar.clouds.length > 0 && (
            <FieldCard
              label="Nubes"
              color="#3ecf7a"
              value={metar.clouds.map(c => `${c.code ?? ''}${c.base_feet_agl ? (c.base_feet_agl / 100).toFixed(0) + '00ft' : ''}`).join(' · ')}
              note={cloudNote(metar.clouds)}
            />
          )}
          {tempC !== undefined && tempC !== null && (
            <FieldCard
              label="Temperatura"
              color="#ff9966"
              value={`${tempC}°C / Rocío ${dewC}°C`}
              note={diff !== null ? `Diferencia Temp–Rocío: ${diff}°C${diff < 3 ? ' — riesgo de niebla' : ''}` : 'Temperatura registrada'}
            />
          )}
          {qnhHpa !== undefined && (
            <FieldCard
              label="QNH"
              color="#bb88ff"
              value={`${qnhHpa} hPa`}
              note={qnhHpa < 980 ? 'Presión muy baja — sistema de baja activo' : qnhHpa > 1030 ? 'Presión alta — tiempo estable' : 'Presión normal'}
            />
          )}
        </div>
      </div>

      {/* TAF */}
      {taf && (
        <div>
          <p className="text-[.67rem] font-medium tracking-widest uppercase mb-1.5" style={{ color: 'var(--color-muted-foreground)', opacity: 0.5 }}>
            TAF — Pronóstico
          </p>
          <div
            className="rounded-md px-5 py-4 overflow-x-auto text-[.82rem] leading-[1.8]"
            style={{ fontFamily: 'monospace', color: '#c8e6ff', background: '#020810', border: '1px solid var(--color-border)' }}
          >
            {taf}
          </div>
        </div>
      )}

      {metar.observed && (
        <p className="text-right text-[.67rem]" style={{ color: 'var(--color-muted-foreground)', opacity: 0.4 }}>
          Reporte emitido: {new Date(metar.observed).toUTCString()}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ICAO Modal
// ---------------------------------------------------------------------------

function IcaoModal({
  open,
  onClose,
  onSelect,
}: {
  open: boolean
  onClose: () => void
  onSelect: (code: string) => void
}) {
  const [region, setRegion] = useState('all')
  const [search, setSearch] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      const t = setTimeout(() => searchRef.current?.focus(), 80)
      return () => clearTimeout(t)
    }
  }, [open])

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const q = search.trim().toLowerCase()
  const filtered = ICAO_DB.filter(a => {
    const matchRegion = region === 'all' || a.region === region
    const matchSearch = !q || a.code.toLowerCase().includes(q) || a.city.toLowerCase().includes(q) || a.full.toLowerCase().includes(q) || a.country.toLowerCase().includes(q)
    return matchRegion && matchSearch
  })

  // Group by country when showing all with no search
  const grouped: Record<string, IcaoEntry[]> = {}
  if (region === 'all' && !q) {
    filtered.forEach(a => {
      if (!grouped[a.country]) grouped[a.country] = []
      grouped[a.country].push(a)
    })
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(2,8,16,.85)', backdropFilter: 'blur(6px)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-xl flex flex-col rounded-xl overflow-hidden"
        style={{ maxHeight: '85vh', background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'var(--color-border)' }}>
          <div>
            <div className="font-normal text-lg" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}>
              Códigos ICAO
            </div>
            <div className="text-[.68rem] mt-0.5" style={{ color: 'var(--color-muted-foreground)' }}>
              Hacé clic en una ciudad para cargarla
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-xl px-2 transition-colors cursor-pointer"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            ✕
          </button>
        </div>

        {/* Search */}
        <div className="px-4 pt-4 pb-2">
          <input
            ref={searchRef}
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar ciudad o código ICAO…"
            className="w-full rounded px-3 py-2 text-[.82rem] outline-none transition-colors"
            style={{
              background: '#060d1a',
              border: '1px solid var(--color-border)',
              color: 'var(--color-foreground)',
            }}
            onFocus={e => { e.currentTarget.style.borderColor = '#c8a84b' }}
            onBlur={e => { e.currentTarget.style.borderColor = 'var(--color-border)' }}
          />
        </div>

        {/* Region tabs */}
        <div className="px-4 pb-3 flex gap-1.5 flex-wrap">
          {REGIONS.map(r => (
            <button
              key={r.id}
              onClick={() => { setRegion(r.id); setSearch('') }}
              className="text-[.68rem] font-medium px-3 py-1 rounded-full border cursor-pointer transition-all whitespace-nowrap"
              style={{
                background: region === r.id ? '#c8a84b' : 'transparent',
                color: region === r.id ? '#060d1a' : 'var(--color-muted-foreground)',
                borderColor: region === r.id ? '#c8a84b' : 'var(--color-border)',
              }}
            >
              {r.label}
            </button>
          ))}
        </div>

        {/* List */}
        <div className="overflow-y-auto flex-1 px-2 pb-3">
          {filtered.length === 0 ? (
            <p className="text-[.78rem] text-center py-8" style={{ color: 'var(--color-muted-foreground)' }}>Sin resultados</p>
          ) : region === 'all' && !q ? (
            Object.entries(grouped).map(([country, airports]) => (
              <div key={country}>
                <div
                  className="text-[.6rem] font-medium tracking-[.15em] uppercase px-2 py-2"
                  style={{ color: 'rgba(42,74,112,.9)' }}
                >
                  {country}
                </div>
                {airports.map(a => <IcaoRow key={a.code} item={a} onSelect={onSelect} />)}
              </div>
            ))
          ) : (
            filtered.map(a => <IcaoRow key={a.code} item={a} onSelect={onSelect} />)
          )}
        </div>
      </div>
    </div>
  )
}

function IcaoRow({ item, onSelect }: { item: IcaoEntry; onSelect: (code: string) => void }) {
  return (
    <div
      className="flex items-center justify-between px-2 py-2.5 rounded cursor-pointer transition-colors"
      onClick={() => onSelect(item.code)}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(200,168,75,.08)' }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
    >
      <div className="flex items-center gap-3">
        <span className="text-[.82rem] font-medium min-w-[52px]" style={{ fontFamily: 'monospace', color: '#c8a84b' }}>
          {item.code}
        </span>
        <div>
          <div className="text-[.8rem]" style={{ color: 'var(--color-foreground)' }}>{item.city}</div>
          <div className="text-[.68rem]" style={{ color: 'var(--color-muted-foreground)' }}>{item.full}</div>
        </div>
      </div>
      <span className="text-[.68rem]" style={{ color: 'var(--color-muted-foreground)', opacity: 0.5 }}>{item.country}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// METAR widget (query form + result)
// ---------------------------------------------------------------------------

function MetarWidget() {
  const [icao, setIcao]       = useState('')
  const [loading, setLoading] = useState(false)
  const [metar, setMetar]     = useState<MetarData | null>(null)
  const [taf, setTaf]         = useState<string | null>(null)
  const [error, setError]     = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const fetchTAF = useCallback(async (code: string) => {
    try {
      const res = await fetch(`/api/metar?icao=${encodeURIComponent(code)}&type=taf`)
      if (!res.ok) return
      const data = await res.json()
      if (data.data?.[0]?.raw_text) setTaf(data.data[0].raw_text)
    } catch { /* TAF is optional */ }
  }, [])

  const doFetch = useCallback(async (code: string) => {
    const clean = code.trim().toUpperCase()
    if (clean.length < 4) return
    setLoading(true)
    setMetar(null)
    setTaf(null)
    setError(null)
    try {
      const res = await fetch(`/api/metar?icao=${encodeURIComponent(clean)}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (!data.data || data.data.length === 0) throw new Error(`ICAO ${clean} no encontrado`)
      setMetar(data.data[0])
      fetchTAF(clean)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setLoading(false)
    }
  }, [fetchTAF])

  function handleSelect(code: string) {
    setIcao(code)
    setModalOpen(false)
    doFetch(code)
  }

  return (
    <>
      <div
        className="rounded-xl p-6"
        style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
      >
        <h2
          className="text-xl font-normal mb-1"
          style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
        >
          Consultá el METAR de tu aeródromo
        </h2>
        <p className="text-[.78rem] mb-5" style={{ color: 'var(--color-muted-foreground)' }}>
          Ingresá el código ICAO de 4 letras (ej. SAEZ, LEMD, KJFK, EGLL)
        </p>

        <div className="flex gap-3 flex-wrap">
          <input
            type="text"
            maxLength={4}
            placeholder="SAEZ"
            value={icao}
            onChange={e => setIcao(e.target.value.toUpperCase())}
            onKeyDown={e => { if (e.key === 'Enter') doFetch(icao) }}
            className="flex-1 min-w-[120px] rounded px-4 py-2.5 text-[1rem] tracking-[.25em] uppercase placeholder-slate-600 outline-none transition-all"
            style={{
              background: 'var(--color-background)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-foreground)',
              fontFamily: 'monospace',
            }}
            onFocus={e => { e.currentTarget.style.borderColor = '#c8a84b'; e.currentTarget.style.boxShadow = '0 0 0 2px rgba(200,168,75,.15)' }}
            onBlur={e => { e.currentTarget.style.borderColor = 'var(--color-border)'; e.currentTarget.style.boxShadow = 'none' }}
          />
          <button
            onClick={() => setModalOpen(true)}
            className="px-4 py-2.5 rounded text-[.78rem] transition-colors cursor-pointer"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-muted-foreground)', background: 'transparent' }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(200,168,75,.5)'; (e.currentTarget as HTMLElement).style.color = '#c8a84b' }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-border)'; (e.currentTarget as HTMLElement).style.color = 'var(--color-muted-foreground)' }}
          >
            🔍 Ver ICAO
          </button>
          <button
            onClick={() => doFetch(icao)}
            disabled={loading}
            className="px-6 py-2.5 rounded text-[.82rem] font-medium transition-colors cursor-pointer flex items-center gap-2 disabled:opacity-60"
            style={{ background: '#c8a84b', color: '#060d1a' }}
          >
            {loading ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
                Consultando…
              </>
            ) : 'Consultar METAR'}
          </button>
        </div>

        <p className="mt-3 text-[.67rem]" style={{ color: 'var(--color-muted-foreground)', opacity: 0.4 }}>
          Datos provistos por{' '}
          <a href="https://www.checkwx.com" target="_blank" rel="noopener noreferrer" className="underline hover:opacity-100 transition-opacity">
            CheckWX
          </a>.
        </p>
      </div>

      {/* Results */}
      {error && (
        <div
          className="mt-6 rounded-xl p-5 text-[.85rem]"
          style={{ background: 'rgba(26,10,10,.8)', border: '1px solid rgba(192,57,43,.4)', color: '#e05545' }}
        >
          <span className="font-medium">No se pudo obtener el METAR.</span>{' '}
          <span style={{ opacity: 0.7 }}>{error}</span>
          <p className="mt-2 text-[.75rem]" style={{ color: 'rgba(192,57,43,.7)' }}>
            Verificá el código ICAO o revisá la conexión.
          </p>
        </div>
      )}

      {metar && (
        <div className="mt-6 animate-[fadeUp_.35s_ease_both]">
          <MetarResult metar={metar} taf={taf} />
        </div>
      )}

      <IcaoModal key={String(modalOpen)} open={modalOpen} onClose={() => setModalOpen(false)} onSelect={handleSelect} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Examples section (3 tabs)
// ---------------------------------------------------------------------------

type ExKey = 'saez' | 'egll' | 'kjfk'

const EXAMPLES: Array<{ id: ExKey; label: string; tokens: Token[]; fields: Array<{ label: string; color: string; value: string; note: string }> }> = [
  {
    id: 'saez',
    label: '🇦🇷 SAEZ — Ezeiza (buen tiempo)',
    tokens: [
      { text: 'METAR ' }, { text: 'SAEZ', color: C.station }, { text: ' ' },
      { text: '021300Z', color: C.time }, { text: ' ' },
      { text: '18015KT 170V210', color: C.wind }, { text: ' ' },
      { text: '9999', color: C.vis }, { text: ' ' },
      { text: 'FEW020 SCT060', color: C.cloud }, { text: ' ' },
      { text: '22/14', color: C.temp }, { text: ' ' },
      { text: 'Q1018', color: C.qnh }, { text: ' NOSIG' },
    ],
    fields: [
      { label: 'Viento',       color: C.wind,  value: '18015KT 170V210', note: '180° a 15 kt, variable entre 170° y 210°. Viento del sur moderado, sin ráfagas.' },
      { label: 'Visibilidad',  color: C.vis,   value: '9999',             note: 'Excelente — más de 10 km. VFR sin restricciones.' },
      { label: 'Nubes',        color: C.cloud, value: 'FEW020 SCT060',   note: 'Pocas nubes a 2.000 ft, dispersas a 6.000 ft. Techo amplio, sin preocupación.' },
      { label: 'Categoría',    color: C.cloud, value: 'VFR',              note: 'Condiciones ideales. NOSIG indica sin cambio significativo esperado.' },
    ],
  },
  {
    id: 'egll',
    label: '🇬🇧 EGLL — Heathrow (niebla)',
    tokens: [
      { text: 'METAR ' }, { text: 'EGLL', color: C.station }, { text: ' ' },
      { text: '021400Z', color: C.time }, { text: ' ' },
      { text: '26005KT', color: C.wind }, { text: ' ' },
      { text: '0600', color: C.vis }, { text: ' ' },
      { text: 'FG', color: C.phenom }, { text: ' ' },
      { text: 'OVC002', color: C.cloud }, { text: ' ' },
      { text: '09/09', color: C.temp }, { text: ' ' },
      { text: 'Q1024', color: C.qnh },
    ],
    fields: [
      { label: 'Visibilidad', color: '#e05545', value: '0600',   note: 'Solo 600 metros. Condición de niebla (FG). Aproximación visual imposible.' },
      { label: 'Nubes',       color: '#e05545', value: 'OVC002', note: 'Cielo cubierto (OVC) a 200 ft. Techo extremadamente bajo — mínimas CAT III.' },
      { label: 'Temp/Rocío',  color: C.temp,   value: '09/09',  note: 'Temperatura igual al punto de rocío — saturación completa. Niebla garantizada.' },
      { label: 'Categoría',   color: '#cc66ff', value: 'LIFR',   note: 'Low IFR. Solo opera con sistemas de aterrizaje automático CAT IIIb.' },
    ],
  },
  {
    id: 'kjfk',
    label: '🇺🇸 KJFK — JFK (tormenta)',
    tokens: [
      { text: 'METAR ' }, { text: 'KJFK', color: C.station }, { text: ' ' },
      { text: '151845Z', color: C.time }, { text: ' ' },
      { text: '23028G45KT', color: C.wind }, { text: ' ' },
      { text: '2SM', color: C.vis }, { text: ' ' },
      { text: 'TSRA', color: C.phenom }, { text: ' ' },
      { text: 'BKN012CB OVC030', color: C.cloud }, { text: ' ' },
      { text: '18/16', color: C.temp }, { text: ' ' },
      { text: 'A2965', color: C.qnh },
    ],
    fields: [
      { label: 'Viento',    color: '#e05545', value: '23028G45KT',    note: '230° a 28 kt con ráfagas de 45 kt. Viento de tormenta — windshear probable.' },
      { label: 'Fenómeno',  color: '#e05545', value: 'TSRA',           note: 'Thunderstorm with Rain — tormenta eléctrica con lluvia activa.' },
      { label: 'Nubes',     color: '#e05545', value: 'BKN012CB',       note: 'Nubosidad rota a 1.200 ft con Cumulonimbus — máxima alerta operacional.' },
      { label: 'Categoría', color: '#e05545', value: 'IFR',            note: 'Solo IFR. Muchos operadores aplican Hold o desvían a alternado con TS activa.' },
    ],
  },
]

function ExamplesSection() {
  const [active, setActive] = useState<ExKey>('saez')
  const ex = EXAMPLES.find(e => e.id === active)!

  return (
    <section>
      <h2
        className="text-2xl italic font-normal mb-1"
        style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
      >
        Ejemplos reales anotados
      </h2>
      <p className="text-[.74rem] mb-6" style={{ color: 'var(--color-muted-foreground)' }}>
        Tres situaciones meteorológicas distintas — leelas campo por campo
      </p>

      <div className="flex gap-2 mb-5 flex-wrap">
        {EXAMPLES.map(e => (
          <button
            key={e.id}
            onClick={() => setActive(e.id)}
            className="px-4 py-1.5 rounded-full text-[.72rem] transition-all cursor-pointer border"
            style={{
              background: active === e.id ? '#c8a84b' : 'transparent',
              color: active === e.id ? '#060d1a' : 'var(--color-muted-foreground)',
              borderColor: active === e.id ? '#c8a84b' : 'var(--color-border)',
              fontWeight: active === e.id ? 600 : 400,
            }}
          >
            {e.label}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        <MetarRaw tokens={ex.tokens} size="sm" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {ex.fields.map(f => (
            <FieldCard key={f.label} label={f.label} color={f.color} value={f.value} note={f.note} />
          ))}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Glosario
// ---------------------------------------------------------------------------

const GLOSARIO = [
  { code: 'TS',       color: '#e05545', note: 'Thunderstorm — tormenta eléctrica' },
  { code: 'TSRA',     color: '#e05545', note: 'Tormenta con lluvia' },
  { code: 'GR',       color: '#e05545', note: 'Granizo' },
  { code: 'FG',       color: '#5aaad8', note: 'Fog — niebla (<1000 m)' },
  { code: 'BR',       color: '#5aaad8', note: 'Mist — neblina (1000–5000 m)' },
  { code: 'RA',       color: '#5aaad8', note: 'Rain — lluvia' },
  { code: 'SN',       color: '#90aabb', note: 'Snow — nieve' },
  { code: 'DZ',       color: '#90aabb', note: 'Drizzle — llovizna' },
  { code: 'HZ',       color: '#f0a030', note: 'Haze — calima / bruma seca' },
  { code: 'FC',       color: '#e05545', note: 'Funnel cloud — tornado / tromba' },
  { code: 'FZ',       color: '#90aabb', note: 'Freezing — prefijo de engelamiento (FZRA, FZFG)' },
  { code: 'SKC / CLR',color: '#3ecf7a', note: 'Sky clear — cielo despejado' },
  { code: 'FEW',      color: '#3ecf7a', note: '1–2 octas de cobertura' },
  { code: 'SCT',      color: '#c8a84b', note: 'Scattered — 3–4 octas' },
  { code: 'BKN',      color: '#f0a030', note: 'Broken — 5–7 octas' },
  { code: 'OVC',      color: '#e05545', note: 'Overcast — 8 octas (cubierto)' },
  { code: 'VV',       color: '#e05545', note: 'Vertical visibility — sin techo definido' },
  { code: '-RA / +RA',color: '#5aaad8', note: 'Light / heavy rain. − = leve, + = fuerte' },
  { code: 'CAVOK',    color: '#3ecf7a', note: 'Ceiling And Visibility OK — vis >10km, sin nubes <5000ft, sin fenómenos' },
  { code: 'NOSIG',    color: '#90aabb', note: 'No significant change expected — sin cambios en 2 horas' },
  { code: 'WS',       color: '#f0a030', note: 'Wind shear — cizalladura reportada en aproximación o despegue' },
  { code: 'CB / TCU', color: '#e05545', note: 'Cumulonimbus / Towering Cumulus — siempre crítico' },
  { code: 'TEMPO',    color: '#f0a030', note: 'Cambio temporal de <1 hora, durante <mitad del período' },
  { code: 'BECMG',    color: '#f0a030', note: 'Becoming — cambio gradual y permanente hacia nuevas condiciones' },
]

function GlosarioSection() {
  const [open, setOpen] = useState(false)
  return (
    <section>
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center justify-between w-full cursor-pointer group text-left"
      >
        <div>
          <h2
            className="text-2xl italic font-normal transition-colors"
            style={{ fontFamily: 'var(--font-serif)', color: open ? '#c8a84b' : 'var(--color-foreground)' }}
          >
            Glosario de códigos frecuentes
          </h2>
          <p className="text-[.74rem] mt-0.5" style={{ color: 'var(--color-muted-foreground)' }}>
            Fenómenos, coberturas y abreviaturas más comunes {open ? '▴' : '▾'}
          </p>
        </div>
      </button>

      {open && (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 mt-6">
          {GLOSARIO.map(g => (
            <div
              key={g.code}
              className="rounded-md p-3 transition-colors"
              style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(42,74,112,.8)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-border)' }}
            >
              <div className="text-[.88rem] mb-1" style={{ fontFamily: 'monospace', color: g.color }}>
                {g.code}
              </div>
              <p className="text-[.72rem] leading-[1.55]" style={{ color: 'var(--color-muted-foreground)' }}>
                {g.note}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Divider
// ---------------------------------------------------------------------------

function Divider() {
  return <hr className="border-t" style={{ borderColor: 'var(--color-border)' }} />
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Metar() {
  return (
    <div className="relative">
      <Dither opacity={0.03} />

      <FadeContent>
        {/* Hero */}
        <div
          className="text-center px-2 pt-6 pb-10 border-b"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <p
            className="inline-flex items-center gap-3 text-[.62rem] font-medium tracking-[.28em] uppercase mb-4"
            style={{ color: '#c8a84b' }}
          >
            <span className="block w-7 h-px" style={{ background: 'rgba(110,88,32,.6)' }} />
            Meteorología operacional
            <span className="block w-7 h-px" style={{ background: 'rgba(110,88,32,.6)' }} />
          </p>
          <h1
            className="text-4xl sm:text-6xl font-normal leading-[1.08]"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            METAR <em style={{ color: '#c8a84b' }}>&</em> TAF
          </h1>
          <p
            className="mt-4 text-[.93rem] max-w-xl mx-auto leading-[1.8]"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            El lenguaje cifrado del clima aeronáutico. Aprendé a leerlo campo por campo — y consultá el reporte real de cualquier aeródromo del mundo.
          </p>
        </div>

        {/* Live widget */}
        <div className="mt-10 max-w-2xl mx-auto">
          <MetarWidget />
        </div>

        <div className="mt-12 space-y-12">

          <Divider />

          {/* ¿Qué es un METAR? */}
          <section>
            <h2
              className="text-2xl italic font-normal mb-1"
              style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
            >
              ¿Qué es un METAR?
            </h2>
            <p className="text-[.74rem] mb-8" style={{ color: 'var(--color-muted-foreground)' }}>
              Meteorological Aerodrome Report — reporte rutinario de condiciones actuales
            </p>

            <MetarRaw size="sm" tokens={[
              { text: 'SAEZ', color: C.station }, { text: ' ' },
              { text: '021300Z', color: C.time }, { text: ' ' },
              { text: '18015KT', color: C.wind }, { text: ' ' },
              { text: '9999', color: C.vis }, { text: ' ' },
              { text: 'FEW020 SCT060 BKN100', color: C.cloud }, { text: ' ' },
              { text: '22/14', color: C.temp }, { text: ' ' },
              { text: 'Q1018', color: C.qnh }, { text: ' NOSIG' },
            ]} />

            {/* Color legend */}
            <div className="flex flex-wrap gap-2 mt-4 text-[.68rem] font-medium">
              {[
                { label: '🏛 Estación ICAO', color: C.station },
                { label: '🕐 Fecha/Hora UTC', color: C.time },
                { label: '💨 Viento',         color: C.wind },
                { label: '👁 Visibilidad',    color: C.vis },
                { label: '☁ Nubes',          color: C.cloud },
                { label: '🌡 Temp/Rocío',     color: C.temp },
                { label: '📏 QNH',           color: C.qnh },
              ].map(item => (
                <span
                  key={item.label}
                  className="px-2.5 py-1 rounded border"
                  style={{ color: item.color, background: 'var(--color-card)', borderColor: 'var(--color-border)' }}
                >
                  {item.label}
                </span>
              ))}
            </div>

            {/* Field cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-6">
              <FieldCard label="Estación" color={C.station} value="SAEZ" note="Código ICAO de 4 letras del aeródromo. SAEZ = Ezeiza (Buenos Aires). LEMD = Madrid. KJFK = Nueva York JFK." />
              <FieldCard label="Fecha y hora" color={C.time} value="021300Z" note="Día del mes (02) + hora (1300) + Z de Zulú (UTC). Siempre en UTC, nunca hora local." />
              <FieldCard label="Viento" color={C.wind} value="18015KT" note="Dirección (180° = Sur) + velocidad (15 nudos). Si hay ráfagas: 18015G28KT. Viento variable: VRB05KT. Calma: 00000KT." />
              <FieldCard label="Visibilidad" color={C.vis} value="9999" note="En metros. 9999 = 10 km o más (visibilidad máxima). 0600 = 600 m. Aeropuertos USA usan millas: 10SM, 1/4SM." />
              <FieldCard label="Nubes" color={C.cloud} value="FEW020 SCT060 BKN100" note="Cobertura + altura en centenas de pies. FEW = 1–2 octas · SCT = 3–4 · BKN = 5–7 · OVC = 8. 020 = 2.000 ft AGL." />
              <FieldCard label="Temperatura / Punto de rocío" color={C.temp} value="22/14" note="Temperatura actual (22°C) / Punto de rocío (14°C). Cuando se acercan → niebla inminente. M indica negativo: M03 = −3°C." />
              <FieldCard label="QNH" color={C.qnh} value="Q1018" note="Presión al nivel del mar en hPa. Crítico para la altimetría: el piloto ajusta el altímetro a este valor para leer alturas correctas." />
              <FieldCard label="Tendencia / Fenómenos" color="#90aabb" value="NOSIG · TEMPO · BECMG" note="NOSIG = sin cambio significativo. TEMPO = cambio temporal. BECMG = cambio gradual hacia X condición. TS = tormenta. FG = niebla." />
            </div>
          </section>

          <Divider />

          {/* Categorías de vuelo */}
          <section>
            <h2
              className="text-2xl italic font-normal mb-1"
              style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
            >
              Categorías de vuelo
            </h2>
            <p className="text-[.74rem] mb-8" style={{ color: 'var(--color-muted-foreground)' }}>
              Determinadas por techo de nubes y visibilidad — definen qué tipo de vuelo es posible
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { cat: 'VFR',  sub: 'Visual Flight Rules',      ceiling: 'Techo > 3.000 ft',    vis: 'Visib. > 5 km',   note: 'Vuelo visual sin restricciones' },
                { cat: 'MVFR', sub: 'Marginal VFR',             ceiling: 'Techo 1.000–3.000 ft', vis: 'Visib. 3–5 km',   note: 'Condiciones límite VFR' },
                { cat: 'IFR',  sub: 'Instrument Flight Rules',  ceiling: 'Techo 500–1.000 ft',   vis: 'Visib. 1,6–3 km', note: 'Solo vuelo instrumental' },
                { cat: 'LIFR', sub: 'Low IFR',                  ceiling: 'Techo < 500 ft',       vis: 'Visib. < 1,6 km', note: 'Condiciones muy severas' },
              ].map(item => {
                const s = CAT_STYLES[item.cat]
                return (
                  <div
                    key={item.cat}
                    className="rounded-xl p-4 text-center"
                    style={{ background: s.bg, border: `1px solid ${s.border}` }}
                  >
                    <div className="text-2xl font-normal mb-1" style={{ fontFamily: 'var(--font-serif)', color: s.color }}>
                      {item.cat}
                    </div>
                    <div className="text-[.65rem] font-medium tracking-widest uppercase mb-3" style={{ color: s.color, opacity: 0.7 }}>
                      {item.sub}
                    </div>
                    <div className="text-[.75rem] leading-[1.7]" style={{ color: s.color }}>
                      {item.ceiling}<br />{item.vis}<br />
                      <span style={{ opacity: 0.7 }}>{item.note}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>

          <Divider />

          {/* ¿Qué es un TAF? */}
          <section>
            <h2
              className="text-2xl italic font-normal mb-1"
              style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
            >
              ¿Qué es un TAF?
            </h2>
            <p className="text-[.74rem] mb-8" style={{ color: 'var(--color-muted-foreground)' }}>
              Terminal Aerodrome Forecast — pronóstico de hasta 30 horas para un aeródromo
            </p>

            <MetarRaw size="sm" tokens={[
              { text: 'TAF ' }, { text: 'SAEZ', color: C.station }, { text: ' ' },
              { text: '021100Z 0212/0318', color: C.time }, { text: ' ' },
              { text: '19012KT', color: C.wind }, { text: ' ' },
              { text: '9999', color: C.vis }, { text: ' ' },
              { text: 'SCT030', color: C.cloud },
              { text: '\n     TEMPO ' }, { text: '0215/0220', color: C.time }, { text: ' ' },
              { text: '4000', color: C.vis }, { text: ' ' },
              { text: 'TSRA', color: C.phenom }, { text: ' ' },
              { text: 'BKN015CB', color: C.cloud },
              { text: '\n     BECMG ' }, { text: '0300/0302', color: C.time }, { text: ' ' },
              { text: '24008KT', color: C.wind },
            ]} />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-6">
              <FieldCard label="Período de validez" color={C.time} value="0212/0318" note="Día 02 a las 12Z hasta día 03 a las 18Z. El TAF siempre indica desde/hasta en UTC." />
              <FieldCard label="TEMPO" color="#e05545" value="TEMPO 0215/0220" note="Cambio temporal de menos de 1 hora, durante menos de la mitad del período indicado." />
              <FieldCard label="BECMG" color={C.wind} value="BECMG 0300/0302" note="Cambio gradual y permanente hacia nuevas condiciones dentro del período indicado." />
              <FieldCard label="CB en nubes" color="#e05545" value="BKN015CB" note="La sufija CB después de la altura indica Cumulonimbus — la alerta más crítica en cualquier METAR o TAF." />
            </div>
          </section>

          <Divider />

          {/* Ejemplos */}
          <ExamplesSection />

          <Divider />

          {/* Glosario */}
          <GlosarioSection />

        </div>

        {/* Footer note */}
        <div
          className="mt-16 pb-6 text-center text-[.67rem] leading-[2]"
          style={{ color: 'var(--color-muted-foreground)', opacity: 0.4 }}
        >
          Información con fines educativos — consultar NOTAMs y documentación oficial OACI/ANAC para operaciones reales.
        </div>
      </FadeContent>
    </div>
  )
}
