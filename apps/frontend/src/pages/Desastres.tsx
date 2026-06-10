import { useState } from 'react'
import { FadeContent } from '@/components/animated/FadeContent'
import { Dither } from '@/components/animated/Dither'
import { DangerScale } from '../components/ui/DangerScale'

// ---------------------------------------------------------------------------
// Types & Data
// ---------------------------------------------------------------------------

type Family = 'all' | 'geo' | 'hidro' | 'oce'
type BadgeVariant = 'crit' | 'warn' | 'watch' | 'neutral'

interface DisasterCard {
  id: string
  family: Exclude<Family, 'all'>
  title: string
  subtitle: string
  img: string
  imgAlt: string
  tags: string[]
  dangerLevel: 1 | 2 | 3 | 4 | 5
  badge: BadgeVariant
  badgeLabel: string
  description: string
  dateFact: string
  curiosity: string
  action: string
  sources: { label: string; url: string }[]
}

const DISASTERS: DisasterCard[] = [
  {
    id: 'terremotos',
    family: 'geo',
    title: 'Terremotos',
    subtitle: 'Los catastróficos · Sismo · Seísmo',
    img: 'https://upload.wikimedia.org/wikipedia/commons/5/52/2010_Haiti_Earthquake_%28After%29.jpg',
    imgAlt: 'Terremoto — daños en Port-au-Prince, Haiti 2010',
    tags: ['⚡ Corteza terrestre', '🌍 Distribución global', '⏱ 0 segundos de aviso'],
    dangerLevel: 5,
    badge: 'crit',
    badgeLabel: 'Sin aviso · Acción inmediata',
    description: 'El suelo se abre o desplaza súbitamente — edificios colapsan, el polvo llena el aire y las grietas pueden extenderse kilómetros. Liberación súbita de energía acumulada en la corteza terrestre. Puede desencadenar deslizamientos y tsunamis secundarios.',
    dateFact: '1960 Valdivia (Chile), M9.5 — el más poderoso jamás registrado. Dejó 2 millones de personas afectadas y un tsunami que cruzó el Pacífico hasta Japón y Hawaii.',
    curiosity: 'La energía liberada en Valdivia equivale a 178 megatones de TNT — más que la suma de todos los ensayos nucleares de la historia combinados.',
    action: 'Cubrí cabeza y cuello bajo mesa sólida; alejate de ventanas y paredes externas',
    sources: [
      { label: 'USGS Earthquake Map', url: 'https://earthquake.usgs.gov/earthquakes/map/' },
      { label: 'EMSC Europa', url: 'https://www.emsc-csem.org/' },
    ],
  },
  {
    id: 'inundaciones',
    family: 'hidro',
    title: 'Inundaciones',
    subtitle: 'Las que todo lo cubren · Flood',
    img: 'https://images.unsplash.com/photo-1547683905-f686c993aae5?w=600&q=80',
    imgAlt: 'Inundación — calles cubiertas de agua marrón',
    tags: ['💧 Ríos / Lluvias extremas', '🌍 El desastre más frecuente', '⏱ Horas a días de aviso'],
    dangerLevel: 4,
    badge: 'warn',
    badgeLabel: 'Aviso posible · Evacuación prioritaria',
    description: 'El agua marrón sube rápidamente cubriendo calles, casas y vehículos. La corriente puede arrastrar autos sin previo aviso. Desborde de ríos, lluvias extremas o rotura de diques — destruyen infraestructura y contaminan el agua potable durante meses.',
    dateFact: '1931 China — entre 1 y 4 millones de muertos en las inundaciones del Yangtsé y Huang He. La mayor catástrofe hídrica registrada en la historia.',
    curiosity: 'Solo 15 cm de agua en movimiento rápido alcanzan para derribar a un adulto; con 60 cm, un auto es arrastrado — velocidad y profundidad hacen al agua en movimiento más letal que su volumen.',
    action: 'Subí al piso más alto disponible; nunca cruces agua en movimiento a pie ni en auto',
    sources: [
      { label: 'Copernicus Emergency', url: 'https://emergency.copernicus.eu/' },
      { label: 'NOAA Flood Safety', url: 'https://www.noaa.gov/education/resource-collections/weather-atmosphere/floods' },
    ],
  },
  {
    id: 'tornados',
    family: 'hidro',
    title: 'Tornados',
    subtitle: 'Los imprevisibles · Twister · Manga',
    img: 'https://upload.wikimedia.org/wikipedia/commons/9/96/Altus_Oklahoma_Tornado.jpg',
    imgAlt: 'Tornado — columna giratoria en Altus, Oklahoma',
    tags: ['🌪 Hasta 500 km/h', '🌍 75% en EE.UU.', '⏱ Minutos de aviso'],
    dangerLevel: 5,
    badge: 'crit',
    badgeLabel: 'Aviso de minutos · Buscar refugio YA',
    description: 'Columna giratoria de aire visible que desciende desde las nubes hasta el suelo. Puede ser gris oscuro o casi invisible hasta que levanta tierra. Vórtice de hasta 500 km/h que destruye todo en su trayectoria — puede durar segundos o varias horas.',
    dateFact: 'Abril 1973, San Justo (Santa Fe, Argentina) — un tornado EF4 destruyó el 80% de la ciudad, mató al menos 58 personas y dejó 3.000 sin hogar; el más letal documentado en la historia argentina.',
    curiosity: 'El 75% de los tornados del mundo ocurren en EE.UU., en el "Tornado Alley". Argentina tiene la 2ª mayor actividad tornádica del planeta.',
    action: 'Bajá al sótano o habitación interior sin ventanas en planta baja; nunca busques refugio bajo un puente',
    sources: [
      { label: 'NOAA Storm Prediction', url: 'https://www.spc.noaa.gov/' },
      { label: 'NWS Tornado Safety', url: 'https://www.weather.gov/safety/tornado' },
    ],
  },
  {
    id: 'huracanes',
    family: 'hidro',
    title: 'Huracanes',
    subtitle: 'Los gigantes del mar · Ciclón · Tifón',
    img: 'https://upload.wikimedia.org/wikipedia/commons/0/04/Hurricane_Isabel_from_ISS.jpg',
    imgAlt: 'Huracán Isabel — espiral vista desde la ISS, 2003',
    tags: ['🌀 +119 km/h sostenidos', '🌊 Marejadas ciclónicas', '⏱ Días de aviso'],
    dangerLevel: 4,
    badge: 'warn',
    badgeLabel: 'Aviso de días · Evacuación planificada',
    description: 'Desde satélite: espiral perfecta de nubes blancas con ojo central despejado. En tierra: vientos sostenidos, lluvia torrencial y marejadas que inundan costas. Sistema tropical con vientos superiores a 119 km/h que se alimenta del calor oceánico.',
    dateFact: 'Huracán Patricia (octubre 2015, México) — 345 km/h de viento sostenido; el más intenso jamás registrado en el hemisferio occidental según el NHC.',
    curiosity: 'Un huracán maduro libera por día la energía de medio millón de bombas atómicas — toda proveniente únicamente del vapor de agua del océano cálido.',
    action: 'Evacuá la zona costera al menos 48 horas antes del impacto previsto; después de ese plazo, las rutas colapsan',
    sources: [
      { label: 'National Hurricane Center', url: 'https://www.nhc.noaa.gov/' },
      { label: 'IBTrACS Histórico', url: 'https://www.ncei.noaa.gov/products/international-best-track-archive' },
    ],
  },
  {
    id: 'incendios',
    family: 'hidro',
    title: 'Incendios',
    subtitle: 'Los que no tienen freno · Wildfire',
    img: 'https://upload.wikimedia.org/wikipedia/commons/d/d8/Deerfire_high_res_edit.jpg',
    imgAlt: 'Incendio forestal — llamas y cielo naranja (Deer Fire, California)',
    tags: ['🔥 +20 km/h de avance', '🌡 Temperatura + viento + sequía', '⏱ Aviso variable'],
    dangerLevel: 4,
    badge: 'warn',
    badgeLabel: 'Aviso variable · Evacuar si hay orden',
    description: 'Llamas naranjas y rojas consumen árboles a gran velocidad. El cielo se vuelve naranja o rojizo por el humo; la ceniza cae como nieve. Fuego incontrolado impulsado por viento seco, vegetación reseca y temperaturas extremas — puede avanzar más rápido que muchos corredores.',
    dateFact: 'Corrientes, Argentina, enero–febrero 2022 — más de 900.000 hectáreas de humedales y bosque nativo destruidas en semanas; el 13% del territorio provincial quemado, el peor incendio en la historia moderna de la provincia.',
    curiosity: 'Los incendios intensos generan pirocúmulos — nubes de tormenta de hasta 15 km de altura que producen rayos propios y encienden nuevos focos a kilómetros.',
    action: 'Evacuá inmediatamente en dirección contraria al humo y el viento; no volvás a buscar pertenencias',
    sources: [
      { label: 'NASA FIRMS (satélite)', url: 'https://firms.modaps.eosdis.nasa.gov/map/' },
      { label: 'Global Wildfire GWIS', url: 'https://gwis.jrc.ec.europa.eu/' },
    ],
  },
  {
    id: 'tsunamis',
    family: 'oce',
    title: 'Tsunamis',
    subtitle: 'Los de las profundidades · Maremoto',
    img: 'https://upload.wikimedia.org/wikipedia/commons/2/2b/2004_Indian_Ocean_earthquake_Maldives_tsunami_wave.jpg',
    imgAlt: 'Tsunami — ola inundando Malé, Maldivas, 26 diciembre 2004',
    tags: ['🌊 800 km/h en mar abierto', '📍 Costas del Pacífico / Índico', '⏱ Minutos de aviso'],
    dangerLevel: 5,
    badge: 'crit',
    badgeLabel: 'Minutos de aviso · Correr a tierra alta',
    description: 'El mar retrocede metros revelando el fondo antes del golpe; luego llega una pared de agua oscura. La primera ola no es la más grande — siguen series de 5 a 10 olas. Generados por terremotos submarinos, erupciones o deslizamientos: en aguas profundas viajan a 800 km/h.',
    dateFact: '26 de diciembre de 2004, Océano Índico — 230.000 muertos en 14 países. El más letal de la historia moderna, generado por un terremoto de M9.1 frente a Sumatra.',
    curiosity: 'En mar abierto puede tener solo 1 metro de altura viajando a velocidad de avión — completamente imperceptible para barcos en aguas profundas.',
    action: 'Si el mar retrocede rápido sin razón, corré hacia tierra alta sin esperar la alerta oficial',
    sources: [
      { label: 'Pacific Tsunami Warning', url: 'https://tsunami.gov/' },
      { label: 'NOAA Tsunami Research', url: 'https://nctr.pmel.noaa.gov/' },
    ],
  },
  {
    id: 'micro-tsunamis',
    family: 'oce',
    title: 'Micro tsunamis',
    subtitle: 'Los invisibles · Meteotsunami · Seiche',
    img: 'https://upload.wikimedia.org/wikipedia/commons/4/49/High_waves_in_Lake_Michigan_along_the_Chicago_shoreline_%2816807304806%29.jpg',
    imgAlt: 'Olas inusuales en la costa de Chicago sobre el lago Michigan',
    tags: ['🌤 Días soleados, sin tormenta', '⚡ Presión atmosférica', '⏱ Sin aviso en superficie'],
    dangerLevel: 2,
    badge: 'watch',
    badgeLabel: 'Sin aviso aparente · Alejarse del borde',
    description: 'Oleadas irregulares en puertos o costas en días aparentemente tranquilos y soleados. El agua sube y baja en ciclos de minutos sin razón visible. Generadas por cambios bruscos de presión atmosférica o sismos lejanos — pueden alcanzar 1–3 metros en puertos y ensenadas.',
    dateFact: '26 de junio de 1954, lago Michigan (Chicago) — un meteotsunami generó olas de 3 metros que mataron a 8 personas pescando en un día completamente despejado.',
    curiosity: 'A veces el evento meteorológico que los genera está a miles de kilómetros, en otro océano. Pueden producirse sin ninguna tormenta visible a la vista.',
    action: 'Alejate del borde del muelle si el agua oscila irregularmente; no des la espalda al mar',
    sources: [
      { label: 'NOAA Tides & Currents', url: 'https://tidesandcurrents.noaa.gov/' },
      { label: 'DART Buoy Network', url: 'https://www.ndbc.noaa.gov/dart.shtml' },
    ],
  },
  {
    id: 'ola-de-calor',
    family: 'hidro',
    title: 'Ola de calor',
    subtitle: 'Las silenciosas · Heat wave · Canícula',
    img: 'https://upload.wikimedia.org/wikipedia/commons/5/52/Ladakh%2C_India_%2814687115252%29.jpg',
    imgAlt: 'Ola de calor — tierra reseca y agrietada bajo sol extremo',
    tags: ['🌡 +3 días de temperatura extrema', '🌍 Más letal que huracanes por año', '⏱ Aviso de días'],
    dangerLevel: 3,
    badge: 'watch',
    badgeLabel: 'Aviso de días · Hidratarse y buscar fresco',
    description: 'El sol pega sin nubes, el asfalto brilla de calor y el horizonte tiembla con ondas de aire caliente. No hay viento y la noche no refresca. Período de tres o más días con temperaturas muy por encima del promedio histórico — el calor extremo es más letal por año que los tornados, huracanes e inundaciones juntos en la mayoría de países.',
    dateFact: 'Europa, agosto 2003 — ola de calor con temperaturas récord de hasta 47,9°C dejó más de 70.000 muertos en dos semanas, principalmente adultos mayores en Francia e Italia.',
    curiosity: 'El cuerpo humano tolera 48°C en aire seco, pero a 35°C con 100% de humedad la sudoración deja de enfriar y el organismo colapsa en menos de una hora — sin importar la condición física.',
    action: 'Tomá agua antes de sentir sed, cerrá persianas al mediodía y buscá un espacio con aire acondicionado al menos 3 horas por día',
    sources: [
      { label: 'SMN Argentina', url: 'https://www.smn.gob.ar/' },
      { label: 'Copernicus Climate', url: 'https://climate.copernicus.eu/' },
    ],
  },
  {
    id: 'granizo-severo',
    family: 'hidro',
    title: 'Granizo severo',
    subtitle: 'Los proyectiles del cielo · Hailstorm · Pedrisco',
    img: 'https://upload.wikimedia.org/wikipedia/commons/1/1a/Hailstone_deposit_%284_July_2010%3B_Limon%2C_Colorado%2C_USA%29.jpg',
    imgAlt: 'Granizo severo — piedras de hielo de gran tamaño sobre superficie',
    tags: ['🌨 Hasta 150 km/h al caer', '🌍 Argentina lidera el Corredor del Granizo', '⏱ Minutos de aviso'],
    dangerLevel: 3,
    badge: 'watch',
    badgeLabel: 'Aviso de minutos · Buscar cobertura YA',
    description: 'Piedras de hielo caen a más de 150 km/h, rompiendo vidrios, perforando techos y dejando el suelo blanco como si hubiera nevado. Una tormenta puede durar menos de 10 minutos. Formado dentro de cumulonimbos gigantes donde las corrientes ascendentes llevan gotas de agua hasta capas de -50°C — una sola tormenta puede destruir una cosecha entera en minutos.',
    dateFact: 'Córdoba, Argentina, febrero 2015 — granizo de hasta 14 cm de diámetro afectó más de 40.000 viviendas y fue declarado desastre nacional; uno de los eventos más documentados de América del Sur.',
    curiosity: 'El granizo se forma en capas como una cebolla: cada anillo representa un viaje completo de la piedra hacia arriba y abajo dentro de la nube — algunas hacen ese recorrido hasta 25 veces antes de caer.',
    action: 'Entrá al interior de un edificio y alejate de ventanas; con granizo grande, 30 segundos al aire libre pueden romper el parabrisas',
    sources: [
      { label: 'SMN Argentina', url: 'https://www.smn.gob.ar/' },
      { label: 'NOAA Severe Weather', url: 'https://www.weather.gov/safety/thunderstorm-hail' },
    ],
  },
  {
    id: 'erupcion-volcanica',
    family: 'geo',
    title: 'Erupción volcánica',
    subtitle: 'Las que reescriben el paisaje · Volcanic eruption',
    img: 'https://upload.wikimedia.org/wikipedia/commons/6/63/Close_u_of_red_hot_lava_flowing_on_a_dirt_road%2C_a_result_of_the_Kilauea_Volcano_eruption_and_lava_flow_in_2014._-_DPLA_-_ced6ae979602bcc6905f497b87d35e8f.JPG',
    imgAlt: 'Erupción volcánica — ríos de lava y columna de ceniza',
    tags: ['🌋 Hasta 700°C en flujos piroclásticos', '🌍 28 volcanes activos afectan Argentina', '⏱ Aviso variable'],
    dangerLevel: 4,
    badge: 'warn',
    badgeLabel: 'Aviso variable · Evacuá la zona de exclusión',
    description: 'Columnas de ceniza negra suben 20 km y oscurecen el sol durante días; ríos de lava naranja avanzan lentos pero imparables. Los flujos piroclásticos — nubes de gas y roca a 700°C — descienden la ladera a más de 100 km/h. La ceniza puede paralizar aeropuertos a miles de kilómetros y los gases modifican el clima global durante años.',
    dateFact: 'Nevado del Ruiz, Colombia, noviembre 1985 — una erupción moderada fundió parte del glaciar y sepultó la ciudad de Armero en minutos; 23.000 muertos, la tercera erupción más letal del siglo XX.',
    curiosity: 'La erupción del Pinatubo (Filipinas, 1991) enfrió el planeta entero 0,5°C durante dos años al inyectar 20 millones de toneladas de dióxido de azufre en la estratosfera — más que todas las emisiones industriales de ese año.',
    action: 'Si llueve ceniza, cubrí nariz y boca con tela húmeda y sellá puertas y ventanas con cinta; la ceniza fina es más peligrosa que el humo',
    sources: [
      { label: 'Smithsonian Volcanoes', url: 'https://volcano.si.edu/' },
      { label: 'INPRES Argentina', url: 'https://www.inpres.gob.ar/' },
    ],
  },
]

const SECTIONS: { family: Exclude<Family, 'all'>; title: string; subtitle: string }[] = [
  { family: 'geo',   title: 'Geológicos',          subtitle: 'Origen en la corteza terrestre · Cero aviso · Impacto inmediato' },
  { family: 'hidro', title: 'Hidrometeorológicos',  subtitle: 'Agua y atmósfera · Aviso variable · Mayor frecuencia global' },
  { family: 'oce',   title: 'Oceánicos',            subtitle: 'Origen en el mar · Aviso escaso · Velocidad de avión en aguas profundas' },
]

const BADGE_STYLE: Record<BadgeVariant, { color: string; bg: string; border: string }> = {
  crit:    { color: 'var(--color-crit-soft)', bg: 'rgba(255,0,0,.06)',    border: 'rgba(255,0,0,.28)'     },
  warn:    { color: 'var(--color-warn)', bg: 'rgba(192,57,43,.06)',  border: 'rgba(192,57,43,.28)'   },
  watch:   { color: 'var(--color-watch)', bg: 'rgba(212,135,15,.06)', border: 'rgba(212,135,15,.28)'  },
  neutral: { color: '#90aabb', bg: 'rgba(96,112,128,.06)', border: 'rgba(96,112,128,.28)'  },
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Card({ card }: { card: DisasterCard }) {
  const badge = BADGE_STYLE[card.badge]
  return (
    <article className="py-8 border-b last:border-0" style={{ borderColor: 'var(--color-border)' }}>
      <div className="flex flex-col md:flex-row gap-6">
        {/* Image */}
        <div
          className="shrink-0 rounded-xl overflow-hidden"
          style={{ width: '100%', maxWidth: '300px', height: '200px', background: 'var(--color-card)' }}
        >
          <img
            src={card.img}
            alt={card.imgAlt}
            loading="lazy"
            referrerPolicy="no-referrer"
            className="w-full h-full object-cover transition-transform duration-500 hover:scale-105"
          />
        </div>

        {/* Body */}
        <div className="flex-1 flex flex-col gap-3">
          <div>
            <h3 className="text-2xl font-semibold leading-tight mb-1" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}>
              {card.title}
            </h3>
            <p className="text-[.63rem] font-medium tracking-widest uppercase" style={{ color: 'var(--color-primary)' }}>
              {card.subtitle}
            </p>
          </div>

          <div className="flex gap-4 flex-wrap text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
            {card.tags.map(t => <span key={t}>{t}</span>)}
          </div>

          <div>
            <DangerScale level={card.dangerLevel} />
            <div className="mt-2">
              <span
                className="inline-flex items-center gap-1.5 text-[.68rem] font-medium px-2.5 py-1 rounded"
                style={{ color: badge.color, background: badge.bg, border: `1px solid ${badge.border}` }}
              >
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: 'currentColor' }} />
                {card.badgeLabel}
              </span>
            </div>
          </div>

          {/* Action — arriba del texto largo para que sea visible sin scroll */}
          <div
            className="rounded-lg px-4 py-3"
            style={{ background: 'rgba(255,0,0,.04)', border: '1px solid rgba(255,107,107,.18)' }}
          >
            <p className="text-[.63rem] font-medium tracking-widest uppercase mb-1" style={{ color: 'var(--color-warn)' }}>Acción</p>
            <p className="text-sm font-medium" style={{ color: '#fca5a5' }}>{card.action}</p>
          </div>

          <p className="text-sm leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
            {card.description}
          </p>

          {/* Date fact */}
          <p
            className="text-xs italic leading-relaxed pl-3"
            style={{ color: 'var(--color-muted-foreground)', borderLeft: '2px solid rgba(200,168,75,0.2)' }}
          >
            📅 <em>{card.dateFact}</em>
          </p>

          {/* Curiosity */}
          <p
            className="text-xs italic leading-relaxed pl-3"
            style={{ color: 'var(--color-muted-foreground)', borderLeft: '2px solid rgba(200,168,75,0.2)' }}
          >
            💡 <em>{card.curiosity}</em>
          </p>

          {/* Sources */}
          <div className="flex gap-2 flex-wrap">
            {card.sources.map(({ label, url }) => (
              <a
                key={url}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[.68rem] px-3 py-1 rounded transition-colors hover:bg-sky-950"
                style={{ color: 'var(--color-info)', border: '1px solid rgba(43,143,212,.25)' }}
              >
                🔗 {label}
              </a>
            ))}
          </div>
        </div>
      </div>
    </article>
  )
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

const FILTERS: { id: Family; label: string }[] = [
  { id: 'all',   label: 'Todo' },
  { id: 'geo',   label: '🌍 Geológicos' },
  { id: 'hidro', label: '💧 Hidrometeorológicos' },
  { id: 'oce',   label: '🌊 Oceánicos' },
]

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Desastres() {
  const [filter, setFilter] = useState<Family>('all')

  const visible = filter === 'all' ? DISASTERS : DISASTERS.filter(d => d.family === filter)

  return (
    <div className="relative">
      <Dither opacity={0.03} />

      <FadeContent>

        {/* Header editorial — diseño intencional, no usar PageHeader aquí */}
        <div className="mb-8 text-center">
          <p className="text-[.62rem] font-medium tracking-[.28em] uppercase mb-4" style={{ color: 'var(--color-primary)' }}>
            Desastres naturales mundiales
          </p>
          <h1
            className="text-4xl sm:text-5xl font-semibold leading-tight mb-4"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Cuando la Tierra{' '}
            <em style={{ color: 'var(--color-primary)', fontStyle: 'italic' }}>no avisa</em>
          </h1>
          <p className="text-sm max-w-md mx-auto leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
            Diez fenómenos de impacto global. Datos históricos verificados, fuentes oficiales de seguimiento y una sola cosa que hacer.
          </p>
        </div>

        {/* Filter bar */}
        <div className="flex gap-2 flex-wrap mb-8">
          {FILTERS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              className="px-4 py-3 rounded-full text-xs font-medium transition-all"
              style={
                filter === id
                  ? { background: 'var(--color-primary)', color: '#060d1a', border: '1px solid var(--color-primary)' }
                  : { background: 'transparent', color: 'var(--color-muted-foreground)', border: '1px solid var(--color-border)' }
              }
            >
              {label}
            </button>
          ))}
        </div>

        {/* Empty state */}
        {visible.length === 0 && (
          <div className="flex flex-col items-center gap-3 py-20 text-center">
            <span className="text-4xl" style={{ opacity: 0.3 }}>🌍</span>
            <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
              No hay desastres en esta categoría.
            </p>
          </div>
        )}

        {/* Sections */}
        {visible.length > 0 && SECTIONS.map(section => {
          const sectionCards = visible.filter(d => d.family === section.family)
          if (sectionCards.length === 0) return null
          return (
            <div key={section.family}>
              <div
                className="flex items-baseline gap-4 pb-3 mb-2 border-b"
                style={{ borderColor: 'var(--color-border)' }}
              >
                <h2
                  className="text-xl font-semibold italic"
                  style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
                >
                  {section.title}
                </h2>
                <p className="text-xs hidden sm:block" style={{ color: 'var(--color-muted-foreground)' }}>
                  {section.subtitle}
                </p>
              </div>
              {sectionCards.map(card => <Card key={card.id} card={card} />)}
            </div>
          )
        })}

      </FadeContent>
    </div>
  )
}
