import { useState, useRef, useEffect } from 'react'
import { FadeContent } from '@/components/animated/FadeContent'
import { Dither } from '@/components/animated/Dither'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Family = 'all' | 'alta' | 'media' | 'baja' | 'vertical' | 'especial' | 'aero'
type BadgeVariant = 'clear' | 'watch' | 'warn' | 'crit' | 'neutral' | 'info'
type PillVariant = 'danger' | 'caution' | 'note'
type DangerLevel = 1 | 2 | 3 | 4 | 5

interface CloudItem {
  id: string
  family: Exclude<Family, 'all' | 'aero'>
  name: string
  latin: string
  heightTag: string
  height: string
  composition: string
  dangerLevel: DangerLevel
  badge: BadgeVariant
  badgeLabel: string
  imgSrc: string
  imgAlt: string
  description: string
  observeTip: string
  aeroText: string
  curiosity: string
}

interface AeroItem {
  id: string
  name: string
  latin: string
  height: string
  detail: string
  emoji: string
  dangerLevel: DangerLevel
  badge: BadgeVariant
  badgeLabel: string
  description: string
  pills: Array<{ variant: PillVariant; label: string }>
  curiosity: string
}

// ---------------------------------------------------------------------------
// Data — clouds
// ---------------------------------------------------------------------------

const CLOUDS: CloudItem[] = [
  {
    id: 'cirros',
    family: 'alta',
    name: 'Cirros',
    latin: 'Cirrus · Ci',
    heightTag: 'Alta · 6–12 km',
    height: '6.000 – 12.000 m',
    composition: 'Cristales de hielo',
    dangerLevel: 2,
    badge: 'watch',
    badgeLabel: 'Posible cambio en 24–48 hs',
    imgSrc: 'https://cdn.zmescience.com/wp-content/uploads/2017/07/8690313402_5f76f736b3_k-1.jpg',
    imgAlt: 'Cirros — filamentos blancos en cielo azul',
    description: 'Líneas finas y blancas que parecen pintadas con pincel en el azul. Son puro hielo, no agua. Hoy el tiempo es bueno — pero son el primer aviso de que algo viene en camino. Cuanto más se espesan y bajan, más cercano está el cambio.',
    observeTip: 'luz lateral del amanecer o el atardecer — resaltan en dorado',
    aeroText: 'Indican corrientes de chorro cercanas y posibles zonas de CAT en crucero. Preceden frentes que afectarán rutas en las próximas 12–24 hs. Si se espesan hacia el horizonte: el deterioro se acerca.',
    curiosity: 'Cirrus en latín significa "mechón de pelo o bucle". El nombre describe exactamente su aspecto — mirá bien la próxima vez.',
  },
  {
    id: 'cirrostratos',
    family: 'alta',
    name: 'Cirrostratos',
    latin: 'Cirrostratus · Cs',
    heightTag: 'Alta · 6–12 km',
    height: '6.000 – 12.000 m',
    composition: 'Velo continuo de hielo',
    dangerLevel: 2,
    badge: 'watch',
    badgeLabel: 'Lluvia probable en las próximas horas',
    imgSrc: 'https://cdn.zmescience.com/wp-content/uploads/2017/07/cirrostratus-246295_960_720.jpg',
    imgAlt: 'Cirrostratos con halo solar',
    description: 'Un velo blanquecino que cubre todo el cielo como papel translúcido. El sol o la luna producen un halo brillante de 22°— ese anillo luminoso es su firma inconfundible. Cuando ves el halo: es hora de prepararse.',
    observeTip: 'a plena luz del día con sol — el halo es el indicador más claro',
    aeroText: 'Preceden frentes cálidos. Cuanto más bajo y denso el velo, más cercana la lluvia. En ruta, marcan el inicio del deterioro progresivo hacia condiciones IFR.',
    curiosity: 'El halo de 22° ocurre por refracción de la luz en cristales de hielo hexagonales orientados al azar — física perfecta, resultado visual mágico.',
  },
  {
    id: 'cirrocumulos',
    family: 'alta',
    name: 'Cirrocúmulos',
    latin: 'Cirrocumulus · Cc',
    heightTag: 'Alta · 6–12 km',
    height: '6.000 – 12.000 m',
    composition: 'Patrón en escamas · muy efímero',
    dangerLevel: 1,
    badge: 'neutral',
    badgeLabel: 'Señal transitoria — observar evolución',
    imgSrc: 'https://cdn.zmescience.com/wp-content/uploads/2017/07/Cirrocumulus_in_Hong_Kong.jpg',
    imgAlt: 'Cirrocúmulos — patrón de escamas blancas',
    description: 'Pequeñas motas blancas en filas ordenadas, como arroz esparcido en el azul. Cada mota tiene menos de un grado angular de tamaño. Raras y muy efímeras — desaparecen en minutos.',
    observeTip: 'cuando el cielo está mayormente despejado — duran muy poco, aprovechá el momento',
    aeroText: 'Pueden indicar inestabilidad en altitud y turbulencia en aire claro (CAT) a niveles de vuelo. Su corta duración los hace difíciles de anticipar en pronósticos.',
    curiosity: 'Son tan efímeras que raramente duran más de minutos antes de transformarse en cirros o cirrostratos. Si las ves, sacá foto rápido.',
  },
  {
    id: 'altocumulos',
    family: 'media',
    name: 'Altocúmulos',
    latin: 'Altocumulus · Ac',
    heightTag: 'Media · 2–6 km',
    height: '2.000 – 6.000 m',
    composition: 'Agua + algo de hielo',
    dangerLevel: 2,
    badge: 'watch',
    badgeLabel: 'Posible tormenta en horas cálidas',
    imgSrc: 'https://cdn.zmescience.com/wp-content/uploads/2017/07/sky-1430070_960_720.jpg',
    imgAlt: 'Altocúmulos castellanus con torres convectivas',
    description: 'Parches y rollos grises y blancos a media altura. Los Ac castellanus — los que tienen pequeñas torres hacia arriba — son el aviso clásico de tormenta vespertina. Si los ves a la mañana de un día caluroso, guardá el paraguas para la tarde.',
    observeTip: 'mañanas de verano — los castellanus son más visibles antes de que el sol caliente el suelo',
    aeroText: 'Los Ac castellanus matinales son indicador de inestabilidad convectiva: alta probabilidad de Cb en horas cálidas. Los despachos los toman como señal de alerta para rutas de tarde.',
    curiosity: 'Regla de campo: Ac castellanus por la mañana = tormenta vespertina casi garantizada en días calurosos con humedad.',
  },
  {
    id: 'altostratos',
    family: 'media',
    name: 'Altostratos',
    latin: 'Altostratus · As',
    heightTag: 'Media · 2–6 km',
    height: '2.000 – 6.000 m',
    composition: 'Capa uniforme y densa',
    dangerLevel: 3,
    badge: 'warn',
    badgeLabel: 'Lluvia continua en camino',
    imgSrc: 'https://images.unsplash.com/photo-1499956827185-0d63ee78a910?w=900&q=85&fit=crop',
    imgAlt: 'Altostratos — manta gris uniforme sin sombras',
    description: 'Una manta gris sin forma que cubre todo. El sol se ve como a través de vidrio esmerilado — presente, pero sin sombras. El ambiente se siente pesado y cerrado. La lluvia ya viene. Suele seguir a los cirrostratos en el ciclo de un frente.',
    observeTip: 'al mediodía — la diferencia entre "sol difuso" y "sin sol" marca el cambio de capa',
    aeroText: 'Condiciones IFR en aproximación. Reduce el techo progresivamente. Precede al Nimboestrato que puede cerrar completamente la visibilidad en destino. Verificar alternados.',
    curiosity: 'Diferencia práctica: el Altostrato deja pasar algo de luz. Cuando esa poca luz desaparece del todo, ya cambió a Nimboestrato.',
  },
  {
    id: 'estrato',
    family: 'baja',
    name: 'Estrato',
    latin: 'Stratus · St',
    heightTag: 'Baja · 0–2 km',
    height: '0 – 2.000 m',
    composition: 'Capa plana y uniforme',
    dangerLevel: 1,
    badge: 'neutral',
    badgeLabel: 'Día gris — llovizna posible, sin lluvia fuerte',
    imgSrc: 'https://cdn.zmescience.com/wp-content/uploads/2023/02/stratus-fractus-1040x585-1.jpg',
    imgAlt: 'Estrato — capa gris plana y uniforme a baja altura',
    description: 'El cielo gris plano de los días sin drama. Sin forma, sin textura, sin volumen. A veces tan bajo que toca las copas de los árboles o los edificios altos. Trae llovizna fina, raramente lluvia seria.',
    observeTip: 'temprano a la mañana en invierno o días fríos — tienden a levantarse con el calor del sol',
    aeroText: 'Techo bajo que puede limitar operaciones VFR. En aeródromos de montaña o valles puede cerrar completamente el acceso visual. Siempre verificar METAR actualizado antes de salir.',
    curiosity: 'La niebla es técnicamente un Estrato que toca el suelo. Cuando sube y deja de estar a nivel de la calle, se convierte en Estrato bajo.',
  },
  {
    id: 'estratocumulos',
    family: 'baja',
    name: 'Estratocúmulos',
    latin: 'Stratocumulus · Sc',
    heightTag: 'Baja · 0–2 km',
    height: '0 – 2.000 m',
    composition: 'La más común del planeta',
    dangerLevel: 1,
    badge: 'clear',
    badgeLabel: 'Sin riesgo inmediato — tiempo estable',
    imgSrc: 'https://cdn.zmescience.com/wp-content/uploads/2017/07/palm-trees-266438_1920.jpg',
    imgAlt: 'Estratocúmulos — bloques grises agrupados con claros de azul',
    description: 'Bloques y rollos grises con claros de azul entre ellos. No traen mal tiempo serio — son las nubes del "nublado parcial". Las más frecuentes del planeta. Las conocés bien aunque no sabías su nombre.',
    observeTip: 'desde un avión mirando hacia abajo — los ves como un campo de algodón con huecos irregulares',
    aeroText: 'Generalmente permiten VFR con precaución. El peligro surge cuando el techo baja a menos de 1.500 ft AGL. Atención a variaciones rápidas de base en zonas costeras.',
    curiosity: 'Cubren más del 20% de la superficie oceánica en cualquier momento dado. Son las nubes más frecuentes y las más ignoradas de la Tierra.',
  },
  {
    id: 'nimboestrato',
    family: 'baja',
    name: 'Nimboestrato',
    latin: 'Nimbostratus · Ns',
    heightTag: 'Baja · 0–3 km',
    height: '0 – 3.000 m',
    composition: 'Espesa · Lluvia activa continua',
    dangerLevel: 3,
    badge: 'warn',
    badgeLabel: 'Lluvia continua — puede durar muchas horas',
    imgSrc: 'https://cdn.zmescience.com/wp-content/uploads/2017/07/1024px-2014_Nimbostratus_rekadr.jpg',
    imgAlt: 'Nimboestrato — capa oscura y densa con lluvia continua',
    description: 'Oscura, densa, sin forma, sin luz. No viene en ráfagas — viene para quedarse. Si llovió todo el día sin parar, ella es la responsable. El nimbus en su nombre viene del latín y significa simplemente "lluvia" o "nube que llueve".',
    observeTip: 'no hay forma definida ni claros — solo un techo oscuro y uniforme que lo cubre todo',
    aeroText: 'Condiciones IFR severas. Alto riesgo de engelamiento (icing) dentro de la nube. Operaciones solo con IFR aprobado y alternado disponible.',
    curiosity: 'Nimbus en latín: lluvia. Cualquier nube con "nimbo" en el nombre está lloviendo activamente ahora mismo.',
  },
  {
    id: 'cumulo',
    family: 'vertical',
    name: 'Cúmulo',
    latin: 'Cumulus · Cu',
    heightTag: 'Vertical · base 600–2.000 m',
    height: '600 – 2.000 m (base)',
    composition: 'La nube de buen tiempo',
    dangerLevel: 1,
    badge: 'clear',
    badgeLabel: 'Buen tiempo — disfrutá el día',
    imgSrc: 'https://images.unsplash.com/photo-1501630834273-4b5604d2ee31?w=900&q=85&fit=crop',
    imgAlt: 'Cúmulos — nubes blancas esponjosas con base plana en cielo azul',
    description: 'La nube de los dibujos animados. Blanca, esponjosa, base plana como cortada con regla. Si son pequeñas y no crecen en altura: día hermoso. Si empiezan a crecer verticalmente hacia torres cada vez más altas: monitorear. Cumulus en latín: "montón" o "acumulación".',
    observeTip: 'tardes soleadas — se forman cuando el sol calienta el suelo y el aire sube',
    aeroText: 'Humilis (pequeños): VFR óptimo. Mediocris: corrientes ascendentes, turbulencia leve bajo ellos. Congestus (grandes con torres): precursor directo de Cb — monitorear con atención.',
    curiosity: 'La base plana marca exactamente la altura donde el aire ascendente se enfría hasta condensarse. Todos los cúmulos del mismo día tienen la base a la misma altitud.',
  },
  {
    id: 'cumulonimbo',
    family: 'vertical',
    name: 'Cumulonimbo',
    latin: 'Cumulonimbus · Cb',
    heightTag: 'Vertical · hasta 15 km',
    height: '0 – 15.000 m',
    composition: 'La nube de tormenta',
    dangerLevel: 5,
    badge: 'crit',
    badgeLabel: 'Tormenta severa — alejarse y buscar refugio',
    imgSrc: 'https://cdn.zmescience.com/wp-content/uploads/2017/07/dramatic-731245_1920.jpg',
    imgAlt: 'Cumulonimbo — torre masiva con yunque en la cúspide',
    description: 'La nube más poderosa de la atmósfera. Torre masiva que puede alcanzar la estratósfera, con la cúspide aplastada en forma de yunque. Cumulo (montón) + nimbus (lluvia): un montón de lluvia. Rayos, granizo, viento fuerte e intensa precipitación, todo simultáneamente.',
    observeTip: 'la cima en forma de yunque aplastado es inconfundible — indica que tocó la tropopausa',
    aeroText: 'Prohibido penetrar en cualquier condición. Rodear por 20 NM mínimo. Genera windshear, granizo a nivel de crucero, turbulencia severa, engelamiento intenso y rayos. Reportado en SIGMET. Es la principal amenaza meteorológica para la aviación.',
    curiosity: 'Un solo Cb puede contener la energía equivalente a decenas de bombas atómicas en calor latente. El yunque confirma que la columna tocó la tropopausa y se expandió horizontalmente.',
  },
  {
    id: 'lenticular',
    family: 'especial',
    name: 'Nube Lenticular',
    latin: 'Altocumulus lenticularis · Ac len',
    heightTag: 'Especial · Orográfica',
    height: '2.000 – 8.000 m',
    composition: 'Sobre montañas y cordilleras',
    dangerLevel: 2,
    badge: 'watch',
    badgeLabel: 'Vientos fuertes en altura — turbulencia posible',
    imgSrc: 'https://scied.ucar.edu/sites/default/files/media/images/lenticular1_big.jpg',
    imgAlt: 'Nube lenticular — disco perfecto estacionario sobre montaña',
    description: 'Discos o platillos perfectamente definidos que flotan inmóviles sobre montañas. Parecen estáticas pero el viento las atraviesa constantemente — se forman y disuelven en el mismo punto. Lenticularis viene del latín "lens": lente o lentejas, por su forma.',
    observeTip: 'desde valles con vistas a la cordillera — la forma de plato volador es inconfundible',
    aeroText: 'Indican ondas orográficas y turbulencia severa en el sotavento. Las mountain waves pueden extenderse cientos de km. Evitar zonas de rotor bajo las lenticulares.',
    curiosity: 'Son "estacionarias" porque se forman siempre en el mismo punto de la onda: el aire entra frío, se condensa, y se evapora del otro lado — como una nube en loop permanente.',
  },
  {
    id: 'mammatus',
    family: 'especial',
    name: 'Mammatus',
    latin: 'Mamma · bajo Cumulonimbus',
    heightTag: 'Especial · Convectiva',
    height: 'Bajo la base del Cb',
    composition: 'Tormenta severa activa',
    dangerLevel: 5,
    badge: 'crit',
    badgeLabel: 'Tormenta severa en zona — no aproximarse',
    imgSrc: 'https://scied.ucar.edu/sites/default/files/media/images/mammatus_big.jpg',
    imgAlt: 'Mammatus — bolsas colgantes bajo la base de un Cumulonimbo',
    description: 'Bolsas que cuelgan hacia abajo de la base de una nube, como burbujas invertidas o ubres. Espectaculares y perturbadoras. Mamma en latín: ubre o pecho, por su forma característica. Confirman un Cb muy activo en la zona.',
    observeTip: 'siempre están debajo de otro nube — mirá hacia arriba desde un espacio seguro cubierto',
    aeroText: 'Mammatus = Cb activo garantizado. Turbulencia severa, windshear y granizo son altamente probables. No aproximarse. Desviar ruta con margen generoso.',
    curiosity: 'Se forman por corrientes descendentes de aire frío dentro del yunque del Cb — exactamente lo opuesto a cómo se forman la mayoría de las nubes.',
  },
  {
    id: 'niebla',
    family: 'especial',
    name: 'Niebla',
    latin: 'Fog · FG en METAR',
    heightTag: 'Especial · Superficie',
    height: '0 m — toca el suelo',
    composition: 'Visibilidad < 1 km',
    dangerLevel: 3,
    badge: 'warn',
    badgeLabel: 'Visibilidad reducida — peligro en conducción y operaciones',
    imgSrc: 'https://images.unsplash.com/photo-1543968996-ee822b8176ba?w=900&q=85&fit=crop',
    imgAlt: 'Niebla sobre ciudad — visibilidad reducida',
    description: 'Una nube que toca el suelo. La visibilidad horizontal cae a menos de un kilómetro. Ambiente húmedo, silencioso y opaco. Típica al amanecer en valles y zonas bajas cuando la temperatura superficial cae al punto de rocío durante la noche.',
    observeTip: 'desde una colina alta mirando un valle al amanecer — el contraste es espectacular',
    aeroText: 'Principal causa de cancelaciones y desvíos. Puede aparecer súbitamente (radiation fog nocturna). METAR reporta FG cuando visibilidad < 1000 m. Requiere mínimas IFR muy bajas (CAT II/III).',
    curiosity: 'FG en METAR = niebla (<1 km). BR = neblina (1–5 km). Misma física, distintas implicancias operativas.',
  },
]

// ---------------------------------------------------------------------------
// Data — aeronautical phenomena
// ---------------------------------------------------------------------------

const AERO: AeroItem[] = [
  {
    id: 'jet-stream',
    name: 'Corriente en Chorro',
    latin: 'Jet Stream',
    height: 'FL300 – FL390 · 9–12 km',
    detail: '100 – 400+ km/h',
    emoji: '🌬️',
    dangerLevel: 2,
    badge: 'info',
    badgeLabel: 'Invisible — impacto directo en tiempo de vuelo y combustible',
    description: 'Ríos de viento de alta velocidad que fluyen en la tropopausa, completamente invisibles. Volar a favor recorta horas de vuelo; en contra, agota combustible y extiende el tiempo. En invierno polar pueden superar los 400 km/h.',
    pills: [
      { variant: 'caution', label: 'Turbulencia CAT' },
      { variant: 'caution', label: 'Desvío de ruta' },
      { variant: 'note',    label: 'Ahorro de combustible' },
      { variant: 'caution', label: 'Engelamiento posible' },
    ],
    curiosity: 'Los vuelos trasatlánticos de oeste a este son más cortos que el regreso gracias al jet stream polar. El planeta girando literalmente a tu favor.',
  },
  {
    id: 'wind-shear',
    name: 'Cizalladura del Viento',
    latin: 'Wind Shear',
    height: 'Crítico por debajo de 500 ft AGL',
    detail: 'Riesgo principal en final',
    emoji: '⚡',
    dangerLevel: 5,
    badge: 'crit',
    badgeLabel: 'Peligro severo — aproximación y despegue',
    description: 'Cambio brusco de velocidad o dirección del viento en corta distancia. A baja altitud puede hacer perder sustentación en segundos. Invisible y puede aparecer sin aviso. El microburst — su forma más peligrosa — es una corriente descendente bajo un Cb que golpea el suelo y se expande explosivamente.',
    pills: [
      { variant: 'danger',  label: 'Pérdida de sustentación' },
      { variant: 'danger',  label: 'Accidente en aproximación' },
      { variant: 'caution', label: 'Microburst bajo Cb' },
    ],
    curiosity: 'Un avión en final que atraviesa un microburst tiene muy pocos segundos para reaccionar. Los sistemas LLWAS en aeropuertos existen exactamente por esto.',
  },
  {
    id: 'icing',
    name: 'Engelamiento en Vuelo',
    latin: 'Aircraft Icing',
    height: 'Dentro de nubes · 0°C a −20°C',
    detail: 'Alas, sensores, pitot',
    emoji: '🧊',
    dangerLevel: 4,
    badge: 'warn',
    badgeLabel: 'Degradación aerodinámica progresiva',
    description: 'Hielo que se forma sobre alas y sensores al volar dentro de nubes con agua supercooled — agua líquida por debajo de 0°C. Cambia la forma aerodinámica del ala, añade peso y puede bloquear el tubo Pitot. Se acumula en minutos sin que el piloto lo perciba.',
    pills: [
      { variant: 'danger', label: 'Pérdida de sustentación' },
      { variant: 'danger', label: 'Pérdida de indicaciones' },
      { variant: 'note',   label: 'Anti-ice obligatorio' },
    ],
    curiosity: 'Clear ice (hielo transparente): el más peligroso porque no se ve sobre el ala. Rime ice (escarcha blanca): visible, pero igualmente crítico para la aerodinámica.',
  },
  {
    id: 'cat',
    name: 'Turbulencia en Aire Claro',
    latin: 'Clear Air Turbulence · CAT',
    height: 'FL250 – FL450',
    detail: 'Cielo completamente despejado',
    emoji: '〰️',
    dangerLevel: 3,
    badge: 'warn',
    badgeLabel: 'Imposible de ver — ocurre sin nubes ni aviso visual',
    description: 'Turbulencia en cielo completamente despejado — sin nubes, sin indicación visual de ningún tipo. Aparece en los bordes del jet stream donde el viento cambia bruscamente. La única advertencia posible viene de PIREPs (reportes de pilotos) que la encontraron antes.',
    pills: [
      { variant: 'danger', label: 'Sin aviso previo' },
      { variant: 'danger', label: 'Lesiones a pasajeros' },
      { variant: 'note',   label: 'PIREPs son la clave' },
    ],
    curiosity: 'La mayoría de las lesiones graves en vuelo sin accidente son causadas por CAT con pasajeros sin cinturón. Por eso los pilotos piden mantenerlo abrochado incluso con cielo azul perfecto.',
  },
  {
    id: 'wake-turbulence',
    name: 'Estela Turbulenta',
    latin: 'Wake Turbulence',
    height: 'Crítico en despegue y aterrizaje',
    detail: 'Toda aeronave la genera',
    emoji: '🌀',
    dangerLevel: 4,
    badge: 'warn',
    badgeLabel: 'Crítico en separación — puede voltear aeronave pequeña',
    description: 'Todo avión genera dos vórtices invisibles en las puntas de sus alas mientras vuela. Se desplazan hacia abajo y a sotavento lentamente. Una aeronave más pequeña que ingrese en esa estela puede perder el control aunque el cielo esté completamente despejado.',
    pills: [
      { variant: 'danger',  label: 'Pérdida de control' },
      { variant: 'caution', label: 'Persiste hasta 3 min' },
      { variant: 'caution', label: 'Se desplaza a sotavento' },
      { variant: 'note',    label: 'Separación mínima ATC' },
    ],
    curiosity: 'Las estelas de un A380 pueden voltear un avión pequeño varios minutos después de su paso. ATC aplica separaciones mínimas específicas por categoría de peso.',
  },
]

// ---------------------------------------------------------------------------
// Style maps
// ---------------------------------------------------------------------------

const BADGE_STYLES: Record<BadgeVariant, { color: string; bg: string; border: string }> = {
  clear:   { color: '#3ecf7a', bg: 'rgba(39,174,96,.1)',   border: 'rgba(39,174,96,.35)'  },
  watch:   { color: '#f0a030', bg: 'rgba(212,135,15,.1)',  border: 'rgba(212,135,15,.35)' },
  warn:    { color: '#e05545', bg: 'rgba(192,57,43,.1)',   border: 'rgba(192,57,43,.35)'  },
  crit:    { color: '#ff6b6b', bg: 'rgba(255,0,0,.09)',    border: 'rgba(255,0,0,.3)'     },
  neutral: { color: '#90aabb', bg: 'rgba(96,112,128,.1)',  border: 'rgba(96,112,128,.3)'  },
  info:    { color: '#5aaad8', bg: 'rgba(43,143,212,.1)',  border: 'rgba(43,143,212,.3)'  },
}

const PILL_STYLES: Record<PillVariant, { color: string; bg: string; border: string }> = {
  danger:  { color: '#ff6b6b', bg: 'rgba(255,0,0,.06)',    border: 'rgba(255,0,0,.3)'    },
  caution: { color: '#f0a030', bg: 'rgba(212,135,15,.06)', border: 'rgba(212,135,15,.3)' },
  note:    { color: '#5aaad8', bg: 'rgba(43,143,212,.06)', border: 'rgba(43,143,212,.3)' },
}

const DANGER_COLORS: Record<DangerLevel, string> = {
  1: '#27ae60',
  2: '#f0a030',
  3: '#f0a030',
  4: '#e05545',
  5: '#ff3333',
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function DangerScale({ level }: { level: DangerLevel }) {
  const activeColor = DANGER_COLORS[level]
  return (
    <div className="flex gap-[3px] items-center mt-0.5">
      {([1, 2, 3, 4, 5] as const).map(i => (
        <span
          key={i}
          className="flex-1 h-1.5 rounded-sm"
          style={{ background: i <= level ? activeColor : 'var(--color-border)' }}
        />
      ))}
    </div>
  )
}

function StatusBadge({ variant, label }: { variant: BadgeVariant; label: string }) {
  const s = BADGE_STYLES[variant]
  return (
    <span
      className="inline-flex items-center gap-2 px-3 py-1 rounded text-[.68rem] font-medium"
      style={{ color: s.color, background: s.bg, border: `1px solid ${s.border}` }}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />
      {label}
    </span>
  )
}

function CloudCardItem({ cloud }: { cloud: CloudItem }) {
  const [aeroOpen, setAeroOpen] = useState(false)

  return (
    <article
      className="border-b py-8 sm:py-10"
      style={{ borderColor: 'var(--color-border)' }}
    >
      <div className="flex flex-col sm:flex-row gap-0">
        {/* Image */}
        <div
          className="relative rounded overflow-hidden shrink-0 bg-[#0f2240] w-full sm:w-[280px] h-[195px] sm:h-[200px]"
        >
          <img
            className="w-full h-full object-cover transition-transform duration-700 hover:scale-105"
            referrerPolicy="no-referrer"
            src={cloud.imgSrc}
            alt={cloud.imgAlt}
            loading="lazy"
          />
          <span
            className="absolute top-2 left-2 backdrop-blur text-[.58rem] font-medium tracking-widest uppercase text-slate-300 px-2 py-1 rounded-sm"
            style={{ background: 'rgba(6,13,26,.8)', border: '1px solid rgba(255,255,255,.1)' }}
          >
            {cloud.heightTag}
          </span>
        </div>

        {/* Body */}
        <div className="flex flex-col gap-3 justify-center sm:pl-8 pt-5 sm:pt-0">
          <div>
            <div
              className="text-[1.85rem] font-normal leading-tight"
              style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
            >
              {cloud.name}
            </div>
            <div className="text-[.63rem] font-medium tracking-widest uppercase mt-1" style={{ color: '#c8a84b' }}>
              {cloud.latin}
            </div>
          </div>

          <div className="flex gap-5 flex-wrap text-[.75rem]" style={{ color: 'var(--color-muted-foreground)' }}>
            <span>📍 {cloud.height}</span>
            <span>{cloud.composition.startsWith('🧊') || cloud.composition.startsWith('💧') || cloud.composition.startsWith('☀️') || cloud.composition.startsWith('⚡') ? '' : ''}
              {['La nube de tormenta', 'La nube de buen tiempo', 'La más común del planeta'].includes(cloud.composition)
                ? `☁ ${cloud.composition}`
                : cloud.composition.includes('Cristales') ? `🧊 ${cloud.composition}` : `💧 ${cloud.composition}`
              }
            </span>
          </div>

          <div>
            <DangerScale level={cloud.dangerLevel} />
            <div className="mt-1.5">
              <StatusBadge variant={cloud.badge} label={cloud.badgeLabel} />
            </div>
          </div>

          <p className="text-[.87rem] leading-[1.75]" style={{ color: 'var(--color-foreground)', opacity: 0.85 }}>
            {cloud.description}
          </p>

          <div className="flex items-center gap-1.5 text-[.63rem]" style={{ color: '#60819a' }}>
            <span>👁</span>
            <span>Mejor observarlos:</span>
            <span style={{ color: 'var(--color-muted-foreground)', marginLeft: '2px' }}>{cloud.observeTip}</span>
          </div>

          {/* Aero toggle */}
          <button
            className="self-start text-[.68rem] font-medium border rounded-sm px-3 py-1 transition-colors cursor-pointer"
            style={{
              color: '#5aaad8',
              borderColor: 'rgba(43,143,212,.35)',
              background: aeroOpen ? 'rgba(43,143,212,.08)' : 'transparent',
            }}
            onClick={() => setAeroOpen(v => !v)}
          >
            ✈️ Ver significado aeronáutico {aeroOpen ? '▴' : '▾'}
          </button>

          {aeroOpen && (
            <div
              className="rounded p-4 flex flex-col gap-2"
              style={{ background: '#0f2240', border: '1px solid var(--color-border)' }}
            >
              <p className="text-[.8rem] leading-[1.7]" style={{ color: 'var(--color-muted-foreground)' }}>
                {cloud.aeroText}
              </p>
              <p
                className="pl-3 text-[.77rem] italic leading-[1.65]"
                style={{
                  color: 'var(--color-muted-foreground)',
                  opacity: 0.7,
                  borderLeft: '2px solid #5a4515',
                }}
              >
                💡 {cloud.curiosity}
              </p>
            </div>
          )}
        </div>
      </div>
    </article>
  )
}

function AeroCardItem({ item }: { item: AeroItem }) {
  return (
    <article
      className="border-b py-8 sm:py-10"
      style={{ borderColor: 'var(--color-border)' }}
    >
      <div className="flex flex-col sm:flex-row gap-0">
        {/* Placeholder */}
        <div
          className="flex flex-col items-center justify-center rounded shrink-0 w-full sm:w-[280px] h-[160px] sm:h-[200px]"
          style={{ background: '#0f2240', border: '1px solid var(--color-border)' }}
        >
          <span className="text-5xl opacity-20">{item.emoji}</span>
          <p className="text-[.63rem] text-center mt-3 px-6 leading-5" style={{ color: 'var(--color-muted-foreground)', opacity: 0.6 }}>
            Fenómeno invisible — solo detectable por instrumentos y sus efectos
          </p>
        </div>

        {/* Body */}
        <div className="flex flex-col gap-3 justify-center sm:pl-8 pt-5 sm:pt-0">
          <div>
            <div
              className="text-[1.85rem] font-normal leading-tight"
              style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
            >
              {item.name}
            </div>
            <div className="text-[.63rem] font-medium tracking-widest uppercase mt-1" style={{ color: '#c8a84b' }}>
              {item.latin}
            </div>
          </div>

          <div className="flex gap-5 flex-wrap text-[.75rem]" style={{ color: 'var(--color-muted-foreground)' }}>
            <span>📍 {item.height}</span>
            <span>⚠️ {item.detail}</span>
          </div>

          <div>
            <DangerScale level={item.dangerLevel} />
            <div className="mt-1.5">
              <StatusBadge variant={item.badge} label={item.badgeLabel} />
            </div>
          </div>

          <p className="text-[.87rem] leading-[1.75]" style={{ color: 'var(--color-foreground)', opacity: 0.85 }}>
            {item.description}
          </p>

          <div className="flex flex-wrap gap-1.5 mt-0.5">
            {item.pills.map(pill => {
              const s = PILL_STYLES[pill.variant]
              return (
                <span
                  key={pill.label}
                  className="text-[.63rem] font-medium px-2.5 py-0.5 rounded-full border"
                  style={{ color: s.color, background: s.bg, borderColor: s.border }}
                >
                  {pill.label}
                </span>
              )
            })}
          </div>

          <p
            className="pl-3 text-[.77rem] italic leading-[1.65]"
            style={{
              color: 'var(--color-muted-foreground)',
              opacity: 0.7,
              borderLeft: '2px solid #5a4515',
            }}
          >
            💡 {item.curiosity}
          </p>
        </div>
      </div>
    </article>
  )
}

// ---------------------------------------------------------------------------
// Quick ID Guide (collapsible)
// ---------------------------------------------------------------------------

function QuickIdGuide() {
  const [open, setOpen] = useState(false)

  return (
    <div className="mt-6">
      <button
        onClick={() => setOpen(v => !v)}
        className="text-[.72rem] font-medium border rounded-sm px-4 py-1.5 transition-colors cursor-pointer"
        style={{ color: '#c8a84b', borderColor: 'rgba(200,168,75,.35)', background: 'transparent' }}
      >
        🔍 ¿Qué nube estoy viendo? — Guía rápida de identificación {open ? '▴' : '▾'}
      </button>

      {open && (
        <div
          className="max-w-2xl mx-auto mt-4 rounded p-6 text-left"
          style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
        >
          <p className="text-[.78rem] mb-4 italic" style={{ color: 'var(--color-muted-foreground)' }}>
            Respondé estas preguntas en orden:
          </p>
          <div className="space-y-3">
            {[
              {
                color: 'rgba(200,168,75,.6)',
                q: '1. ¿Está muy alta y es muy fina o tenue?',
                answers: [
                  { hint: '→ Sí, filamentos como mechones', name: 'Cirros', nameColor: '#c8a84b' },
                  { hint: '→ Sí, velo que produce halo', name: 'Cirrostratos', nameColor: '#c8a84b' },
                  { hint: '→ Sí, escamitas pequeñas en filas', name: 'Cirrocúmulos', nameColor: '#c8a84b' },
                ],
              },
              {
                color: 'rgba(43,143,212,.5)',
                q: '2. ¿Está a media altura y tiene algo de volumen?',
                answers: [
                  { hint: '→ Capa uniforme, sol difuso', name: 'Altostratos', nameColor: '#5aaad8' },
                  { hint: '→ Parches o rollos más definidos', name: 'Altocúmulos', nameColor: '#5aaad8' },
                ],
              },
              {
                color: 'rgba(144,170,187,.4)',
                q: '3. ¿Es una capa baja y gris sin forma?',
                answers: [
                  { hint: '→ Gris plano, llovizna fina', name: 'Estrato', nameColor: '#90aabb' },
                  { hint: '→ Oscura y lloviendo todo el día', name: 'Nimboestrato', nameColor: '#90aabb' },
                  { hint: '→ Bloques con claros de azul', name: 'Estratocúmulos', nameColor: '#90aabb' },
                ],
              },
              {
                color: 'rgba(39,174,96,.4)',
                q: '4. ¿Tiene forma de coliflor o torre?',
                answers: [
                  { hint: '→ Blanca, pequeña, base plana', name: 'Cúmulo (buen tiempo)', nameColor: '#3ecf7a' },
                  { hint: '→ Enorme, oscura, con yunque en la cima', name: 'Cumulonimbo ⚡', nameColor: '#ff6b6b' },
                ],
              },
              {
                color: 'rgba(212,135,15,.4)',
                q: '5. ¿Tiene una forma inusual?',
                answers: [
                  { hint: '→ Disco perfecto sobre montaña', name: 'Lenticular', nameColor: '#f0a030' },
                  { hint: '→ Bolsas colgando hacia abajo', name: 'Mammatus', nameColor: '#ff6b6b' },
                  { hint: '→ Toca el suelo, visibilidad nula', name: 'Niebla', nameColor: '#90aabb' },
                ],
              },
            ].map(section => (
              <div key={section.q} className="pl-4" style={{ borderLeft: `2px solid ${section.color}` }}>
                <p className="text-[.8rem] font-medium" style={{ color: 'var(--color-foreground)' }}>
                  {section.q}
                </p>
                {section.answers.map(a => (
                  <p key={a.name} className="text-[.75rem] mt-1" style={{ color: 'var(--color-muted-foreground)' }}>
                    {a.hint} →{' '}
                    <span style={{ color: a.nameColor }}>{a.name}</span>
                  </p>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Altitude diagram SVG
// ---------------------------------------------------------------------------

function AltitudeDiagram() {
  return (
    <div className="mt-10 justify-center hidden sm:flex">
      <svg width="560" height="190" viewBox="0 0 560 190" fill="none" xmlns="http://www.w3.org/2000/svg">
        <line x1="60" y1="175" x2="540" y2="175" stroke="#1c3358" strokeWidth="1"/>
        <text x="30" y="179" fill="#4a6882" fontSize="10" textAnchor="end">0 m</text>
        <line x1="60" y1="130" x2="540" y2="130" stroke="#1c3358" strokeWidth="1" strokeDasharray="4,4"/>
        <text x="30" y="134" fill="#4a6882" fontSize="10" textAnchor="end">2 km</text>
        <line x1="60" y1="75" x2="540" y2="75" stroke="#1c3358" strokeWidth="1" strokeDasharray="4,4"/>
        <text x="30" y="79" fill="#4a6882" fontSize="10" textAnchor="end">6 km</text>
        <line x1="60" y1="20" x2="540" y2="20" stroke="#1c3358" strokeWidth="1" strokeDasharray="4,4"/>
        <text x="30" y="24" fill="#4a6882" fontSize="10" textAnchor="end">12 km</text>
        <rect x="70" y="22" width="52" height="50" rx="4" fill="rgba(200,168,75,.12)" stroke="rgba(200,168,75,.35)" strokeWidth="1"/>
        <text x="96" y="51" fill="#c8a84b" fontSize="9" textAnchor="middle" fontWeight="500">Ci · Cs · Cc</text>
        <text x="96" y="63" fill="#8a9ab0" fontSize="8" textAnchor="middle">Altas</text>
        <rect x="140" y="77" width="52" height="50" rx="4" fill="rgba(43,143,212,.1)" stroke="rgba(43,143,212,.3)" strokeWidth="1"/>
        <text x="166" y="106" fill="#5aaad8" fontSize="9" textAnchor="middle" fontWeight="500">As · Ac</text>
        <text x="166" y="118" fill="#8a9ab0" fontSize="8" textAnchor="middle">Medias</text>
        <rect x="210" y="132" width="52" height="40" rx="4" fill="rgba(96,112,128,.12)" stroke="rgba(96,112,128,.35)" strokeWidth="1"/>
        <text x="236" y="156" fill="#90aabb" fontSize="9" textAnchor="middle" fontWeight="500">St · Sc · Ns</text>
        <text x="236" y="167" fill="#8a9ab0" fontSize="8" textAnchor="middle">Bajas</text>
        <rect x="295" y="100" width="44" height="74" rx="4" fill="rgba(39,174,96,.1)" stroke="rgba(39,174,96,.3)" strokeWidth="1"/>
        <text x="317" y="142" fill="#3ecf7a" fontSize="9" textAnchor="middle" fontWeight="500">Cu</text>
        <text x="317" y="167" fill="#8a9ab0" fontSize="8" textAnchor="middle">~3 km</text>
        <rect x="355" y="22" width="44" height="152" rx="4" fill="rgba(255,0,0,.08)" stroke="rgba(255,80,80,.35)" strokeWidth="1"/>
        <text x="377" y="100" fill="#ff6b6b" fontSize="9" textAnchor="middle" fontWeight="500">Cb</text>
        <text x="377" y="113" fill="#8a9ab0" fontSize="8" textAnchor="middle">hasta</text>
        <text x="377" y="124" fill="#8a9ab0" fontSize="8" textAnchor="middle">15 km</text>
        <path d="M345 28 Q377 15 409 28" stroke="rgba(255,80,80,.5)" strokeWidth="1.5" fill="none"/>
        <rect x="420" y="55" width="50" height="30" rx="14" fill="rgba(212,135,15,.1)" stroke="rgba(212,135,15,.3)" strokeWidth="1"/>
        <text x="445" y="74" fill="#f0a030" fontSize="8" textAnchor="middle" fontWeight="500">Lenticular</text>
        <rect x="480" y="158" width="48" height="16" rx="3" fill="rgba(144,170,187,.1)" stroke="rgba(144,170,187,.25)" strokeWidth="1"/>
        <text x="504" y="170" fill="#90aabb" fontSize="8" textAnchor="middle">Niebla</text>
      </svg>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

const NUBES_SUBMENU: Array<{ family: Exclude<Family, 'all' | 'aero'>; label: string }> = [
  { family: 'alta',     label: 'Nubes altas' },
  { family: 'media',    label: 'Nubes medias' },
  { family: 'baja',     label: 'Nubes bajas' },
  { family: 'vertical', label: 'Verticales' },
  { family: 'especial', label: 'Especiales' },
]

function FilterBar({
  active,
  onChange,
}: {
  active: Family
  onChange: (f: Family) => void
}) {
  const [ddOpen, setDdOpen] = useState(false)
  const [nubesLabel, setNubesLabel] = useState('☁ Nubes ▾')
  const ddRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ddRef.current && !ddRef.current.contains(e.target as Node)) {
        setDdOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const isNubesActive = ['alta', 'media', 'baja', 'vertical', 'especial'].includes(active)

  function pillStyle(isActive: boolean): React.CSSProperties {
    return {
      padding: '6px 14px',
      borderRadius: '9999px',
      fontSize: '0.72rem',
      fontWeight: isActive ? 600 : 400,
      border: `1px solid ${isActive ? '#c8a84b' : 'rgba(200,168,75,.25)'}`,
      background: isActive ? 'rgba(200,168,75,.12)' : 'transparent',
      color: isActive ? '#c8a84b' : 'var(--color-muted-foreground)',
      cursor: 'pointer',
      transition: 'all 0.2s ease',
      minHeight: '34px',
      display: 'inline-flex',
      alignItems: 'center',
    }
  }

  return (
    <div
      className="flex flex-wrap gap-2 items-center py-3 rounded-xl px-4 mb-6"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <button
        style={pillStyle(active === 'all')}
        onClick={() => { onChange('all'); setNubesLabel('☁ Nubes ▾') }}
      >
        Todo
      </button>

      {/* Nubes dropdown */}
      <div ref={ddRef} className="relative">
        <button
          style={pillStyle(isNubesActive)}
          onClick={() => setDdOpen(v => !v)}
        >
          {nubesLabel}
        </button>
        {ddOpen && (
          <div
            className="absolute top-full left-0 mt-1.5 z-50 min-w-[148px] rounded-xl overflow-hidden shadow-2xl"
            style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
          >
            {NUBES_SUBMENU.map(item => (
              <button
                key={item.family}
                className="block w-full text-left px-4 py-2 text-[.72rem] transition-colors"
                style={{ color: active === item.family ? '#c8a84b' : 'var(--color-muted-foreground)' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(200,168,75,.06)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                onClick={() => {
                  onChange(item.family)
                  setNubesLabel(`☁ ${item.label} ▾`)
                  setDdOpen(false)
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <button
        style={pillStyle(active === 'aero')}
        onClick={() => { onChange('aero'); setNubesLabel('☁ Nubes ▾') }}
      >
        ✈️ Aeronáutico
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Section header
// ---------------------------------------------------------------------------

const SECTIONS: Array<{ family: Exclude<Family, 'all'>; title: string; subtitle: string }> = [
  { family: 'alta',     title: 'Nubes altas',              subtitle: 'Sobre los 6.000 m · Cristales de hielo · Precursoras de cambio' },
  { family: 'media',    title: 'Nubes medias',             subtitle: '2.000 – 6.000 m · Agua líquida y cristales de hielo' },
  { family: 'baja',     title: 'Nubes bajas',              subtitle: 'Por debajo de los 2.000 m · Principalmente agua líquida' },
  { family: 'vertical', title: 'Nubes verticales',         subtitle: 'Desarrollo vertical desde la superficie hasta la tropopausa' },
  { family: 'especial', title: 'Nubes especiales',         subtitle: 'Formaciones poco comunes con características únicas' },
  { family: 'aero',     title: 'Fenómenos aeronáuticos',   subtitle: 'Lo que no se ve a simple vista pero define la seguridad en vuelo' },
]

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div
      className="flex items-baseline gap-4 mt-12 pb-3 border-b"
      style={{ borderColor: 'var(--color-border)' }}
    >
      <h2
        className="text-2xl italic font-normal"
        style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
      >
        {title}
      </h2>
      <p className="text-[.74rem] hidden sm:block" style={{ color: 'var(--color-muted-foreground)', opacity: 0.5 }}>
        {subtitle}
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Nubes() {
  const [filter, setFilter] = useState<Family>('all')

  const filteredClouds = filter === 'all' || filter === 'aero'
    ? (filter === 'aero' ? [] : CLOUDS)
    : CLOUDS.filter(c => c.family === filter)

  const showAero = filter === 'all' || filter === 'aero'
  const cloudFamiliesVisible = filter === 'all'
    ? (['alta', 'media', 'baja', 'vertical', 'especial'] as const)
    : filter === 'aero'
    ? []
    : [filter as Exclude<Family, 'all' | 'aero'>]

  return (
    <div className="relative">
      <Dither opacity={0.03} />

      <FadeContent>
        {/* Hero */}
        <div className="relative text-center px-2 pt-6 pb-10 border-b" style={{ borderColor: 'var(--color-border)' }}>
          <p
            className="inline-flex items-center gap-3 text-[.62rem] font-medium tracking-[.28em] uppercase mb-5"
            style={{ color: '#c8a84b' }}
          >
            <span className="block w-7 h-px" style={{ background: 'rgba(110,88,32,.6)' }} />
            Catálogo visual del cielo
            <span className="block w-7 h-px" style={{ background: 'rgba(110,88,32,.6)' }} />
          </p>
          <h1
            className="text-5xl sm:text-6xl font-normal leading-[1.06]"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Lo que el cielo<br />
            <em style={{ color: '#c8a84b', fontStyle: 'italic' }}>te está diciendo</em>
          </h1>
          <p className="mt-5 text-[.96rem] max-w-md mx-auto leading-[1.8]" style={{ color: 'var(--color-muted-foreground)' }}>
            Nubes, fenómenos y señales invisibles. Todo lo que pasa allá arriba tiene nombre — y algo que contarte sobre lo que viene.
          </p>

          <AltitudeDiagram />
          <QuickIdGuide />
        </div>

        {/* Filter bar */}
        <div className="mt-8">
          <FilterBar active={filter} onChange={setFilter} />
        </div>

        {/* Cloud sections */}
        {cloudFamiliesVisible.map(family => {
          const sectionClouds = filteredClouds.filter(c => c.family === family)
          if (sectionClouds.length === 0) return null
          const sec = SECTIONS.find(s => s.family === family)!
          return (
            <div key={family}>
              <SectionHeader title={sec.title} subtitle={sec.subtitle} />
              {sectionClouds.map(cloud => (
                <CloudCardItem key={cloud.id} cloud={cloud} />
              ))}
            </div>
          )
        })}

        {/* Aero section */}
        {showAero && (
          <div>
            <SectionHeader
              title={SECTIONS.find(s => s.family === 'aero')!.title}
              subtitle={SECTIONS.find(s => s.family === 'aero')!.subtitle}
            />
            {AERO.map(item => (
              <AeroCardItem key={item.id} item={item} />
            ))}
          </div>
        )}

        {/* Empty state */}
        {filteredClouds.length === 0 && !showAero && (
          <p
            className="text-center py-20 text-lg italic"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-muted-foreground)' }}
          >
            No hay elementos de esa categoría.
          </p>
        )}

        {/* Footer note */}
        <div
          className="mt-16 pb-6 text-center text-[.67rem] leading-[2]"
          style={{ color: 'var(--color-muted-foreground)', opacity: 0.5 }}
        >
          Clasificación basada en el{' '}
          <a
            href="https://cloudatlas.wmo.int"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:opacity-100 transition-opacity"
          >
            Atlas Internacional de Nubes (OMM)
          </a>
          {' '}·{' '}
          Información aeronáutica con fines divulgativos — consultar documentación oficial OACI/ANAC para operaciones reales.
        </div>
      </FadeContent>
    </div>
  )
}
