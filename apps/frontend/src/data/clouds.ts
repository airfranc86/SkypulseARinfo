/**
 * Cloud catalog for the Nubes page: the cards and the altitude diagram read from here, so a height
 * or a phrase is written once. Pure data (no React): `src/lib/cloudSky.ts` and its tests import it under Node.
 */
import type { DangerLevel } from '@/components/ui/DangerScale'

export type CloudFamily = 'alta' | 'media' | 'baja' | 'vertical' | 'especial'
export type BadgeVariant = 'clear' | 'watch' | 'warn' | 'crit' | 'neutral' | 'info'

export type CloudId =
  | 'cirros'
  | 'cirrostratos'
  | 'cirrocumulos'
  | 'altocumulos'
  | 'altostratos'
  | 'estrato'
  | 'estratocumulos'
  | 'nimboestrato'
  | 'cumulo'
  | 'cumulonimbo'
  | 'lenticular'
  | 'mammatus'
  | 'niebla'

/**
 * How a cloud is drawn in the altitude diagram:
 * - `layer`: sits inside the floor that holds its base.
 * - `column`: a vertical strip of its own that crosses floors.
 * - `tower`: the cumulonimbus, from the ground to the top of the scale.
 * - `accessory`: hangs from another cloud (mammatus under the anvil).
 * - `ground`: rests on the ground line (fog).
 */
export type CloudShape = 'layer' | 'column' | 'tower' | 'accessory' | 'ground'

/** Altitude the drawing covers (km above the ground), or the cloud it hangs from. */
export type CloudBand = { baseKm: number; topKm: number } | { hangsUnderAnvilOf: CloudId }

export interface CloudSky {
  shape: CloudShape
  band: CloudBand
  /** Height of the cloud in the diagram; the same text it uses for crossing clouds. */
  rangeLabel: string
  /** Colour of the cloud's drawing and its name in the diagram. */
  accent: string
  /** Name drawn in the diagram when it differs from `name`: a short name or soft hyphens for narrow lanes. */
  label?: string
  /** Line under the name in the diagram, when the default (range for crossing clouds) does not fit. */
  note?: string
}

export interface CloudItem {
  id: CloudId
  family: CloudFamily
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
  sky: CloudSky
}

/** Soft hyphen: lets a long name break inside a narrow diagram lane, invisible otherwise. */
const SHY = '­'

// ---------------------------------------------------------------------------
// Clouds
// ---------------------------------------------------------------------------

export const CLOUDS: readonly CloudItem[] = [
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
    sky: { shape: 'layer', band: { baseKm: 6, topKm: 12 }, rangeLabel: '6–12 km', accent: '#c8a84b' },
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
    sky: { shape: 'layer', band: { baseKm: 6, topKm: 12 }, rangeLabel: '6–12 km', accent: '#c8a84b', label: `Cirro${SHY}stratos` },
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
    sky: { shape: 'layer', band: { baseKm: 6, topKm: 12 }, rangeLabel: '6–12 km', accent: '#c8a84b', label: `Cirro${SHY}cúmulos` },
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
    sky: { shape: 'layer', band: { baseKm: 2, topKm: 6 }, rangeLabel: '2–6 km', accent: '#5aaad8', label: `Alto${SHY}cúmulos` },
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
    sky: { shape: 'layer', band: { baseKm: 2, topKm: 6 }, rangeLabel: '2–6 km', accent: '#5aaad8', label: `Alto${SHY}stratos` },
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
    sky: { shape: 'layer', band: { baseKm: 0, topKm: 2 }, rangeLabel: '0–2 km', accent: '#90aabb' },
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
    sky: { shape: 'layer', band: { baseKm: 0, topKm: 2 }, rangeLabel: '0–2 km', accent: '#90aabb', label: `Estrato${SHY}cúmulos` },
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
    sky: { shape: 'column', band: { baseKm: 0, topKm: 3 }, rangeLabel: '0–3 km', accent: '#90aabb', label: `Nimbo${SHY}estrato` },
  },
  {
    id: 'cumulo',
    family: 'vertical',
    name: 'Cúmulo',
    latin: 'Cumulus · Cu',
    heightTag: 'Vertical · base 600–2.000 m',
    height: 'base 600–2.000 m · cima hasta ~3 km',
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
    sky: { shape: 'column', band: { baseKm: 0.6, topKm: 3 }, rangeLabel: 'base 600–2.000 m · cima hasta ~3 km', accent: '#3ecf7a' },
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
    sky: { shape: 'tower', band: { baseKm: 0, topKm: 15 }, rangeLabel: 'hasta 15 km', accent: '#ff6b6b', label: `Cumulo${SHY}nimbo` },
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
    sky: { shape: 'layer', band: { baseKm: 2, topKm: 8 }, rangeLabel: '2–8 km', accent: '#f0a030', label: `Lenti${SHY}cular` },
  },
  {
    id: 'mammatus',
    family: 'especial',
    name: 'Mammatus',
    latin: 'Mamma · bajo Cumulonimbus',
    heightTag: 'Especial · Convectiva',
    height: 'Bajo el yunque del Cb',
    composition: 'Tormenta severa activa',
    dangerLevel: 5,
    badge: 'crit',
    badgeLabel: 'Tormenta severa en zona — no aproximarse',
    imgSrc: 'https://scied.ucar.edu/sites/default/files/media/images/mammatus_big.jpg',
    imgAlt: 'Mammatus — bolsas colgantes bajo la base de un Cumulonimbo',
    description: 'Bolsas que cuelgan hacia abajo de la base de una nube, como burbujas invertidas o ubres. Espectaculares y perturbadoras. Mamma en latín: ubre o pecho, por su forma característica. Confirman un Cb muy activo en la zona.',
    observeTip: 'siempre están debajo de otra nube — mirá hacia arriba desde un espacio seguro cubierto',
    aeroText: 'Mammatus = Cb activo garantizado. Turbulencia severa, windshear y granizo son altamente probables. No aproximarse. Desviar ruta con margen generoso.',
    curiosity: 'Se forman por corrientes descendentes de aire frío dentro del yunque del Cb — exactamente lo opuesto a cómo se forman la mayoría de las nubes.',
    sky: {
      shape: 'accessory',
      band: { hangsUnderAnvilOf: 'cumulonimbo' },
      rangeLabel: 'bajo el yunque del Cb',
      accent: '#ff6b6b',
      label: `Mamma${SHY}tus`,
      note: 'bajo el yunque',
    },
  },
  {
    id: 'niebla',
    family: 'especial',
    name: 'Niebla',
    latin: 'Fog · FG en METAR',
    heightTag: 'Especial · Superficie',
    height: '0 m — toca el suelo',
    composition: 'Visibilidad menor a 1 km',
    dangerLevel: 3,
    badge: 'warn',
    badgeLabel: 'Visibilidad reducida — peligro en conducción y operaciones',
    imgSrc: 'https://images.unsplash.com/photo-1543968996-ee822b8176ba?w=900&q=85&fit=crop',
    imgAlt: 'Niebla sobre ciudad — visibilidad reducida',
    description: 'Una nube que toca el suelo. La visibilidad horizontal cae a menos de un kilómetro. Ambiente húmedo, silencioso y opaco. Típica al amanecer en valles y zonas bajas cuando la temperatura superficial cae al punto de rocío durante la noche.',
    observeTip: 'desde una colina alta mirando un valle al amanecer — el contraste es espectacular',
    aeroText: 'Principal causa de cancelaciones y desvíos. Puede aparecer súbitamente (radiation fog nocturna). METAR reporta FG cuando visibilidad < 1000 m. Requiere mínimas IFR muy bajas (CAT II/III).',
    curiosity: 'FG en METAR = niebla (<1 km). BR = neblina o bruma (1–5 km). Misma física, distintas implicancias operativas.',
    // topKm only sizes the drawing: a layer a few hundred metres thick, resting on the ground.
    sky: { shape: 'ground', band: { baseKm: 0, topKm: 0.3 }, rangeLabel: '0 m — toca el suelo', accent: '#90aabb', note: 'visibilidad menor a 1 km' },
  },
]

// ---------------------------------------------------------------------------
// Family sections (catalog headings)
// ---------------------------------------------------------------------------

export const CLOUD_FAMILY_SECTIONS: Record<CloudFamily, { title: string; subtitle: string }> = {
  alta:     { title: 'Nubes altas',      subtitle: 'Sobre los 6.000 m · Cristales de hielo · Precursoras de cambio' },
  media:    { title: 'Nubes medias',     subtitle: '2.000 – 6.000 m · Agua líquida y cristales de hielo' },
  baja:     { title: 'Nubes bajas',      subtitle: 'Cerca del suelo · el Nimboestrato llega a unos 3 km · Principalmente agua líquida' },
  vertical: { title: 'Nubes verticales', subtitle: 'Desarrollo vertical desde la superficie hasta la tropopausa' },
  especial: { title: 'Nubes especiales', subtitle: 'Formaciones poco comunes con características únicas' },
}
