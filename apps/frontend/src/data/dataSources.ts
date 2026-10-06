/**
 * Content of the "De dónde salen los datos" page (FRA-347). Pure data, no React, so it can be tested.
 *
 * Every statement here was checked against the code that feeds each tool: `apps/backend/app/services/`
 * and `routers/` (providers, fallbacks, caches) and the "Avanzado" panel of Previsión (consensus wording).
 * Do not add a provider, a frequency or a claim without finding it in code first.
 */

export interface DataSource {
  /** Stable key, also used as the anchor of the section. */
  id: string
  /** Section heading. */
  title: string
  /** Plain-words explanation, rioplatense voseo. */
  summary: string
  /** Who produces the data, as named by the source itself. Empty when the section is not about a provider. */
  providers: readonly string[]
}

export const DATA_SOURCES: readonly DataSource[] = [
  {
    id: 'pronostico',
    title: 'Pronóstico del tiempo',
    summary:
      'El pronóstico de 7 días y el de las próximas horas salen de Open-Meteo, que entrega los modelos numéricos globales GFS (NOAA, EE. UU.) y ECMWF (Europa). GFS se actualiza 4 veces al día y ECMWF 2. Los días 5 a 7 son una tendencia: la lluvia se muestra en franjas y puede cambiar.',
    providers: ['Open-Meteo', 'GFS (NOAA, EE. UU.)', 'ECMWF (Europa)'],
  },
  {
    id: 'consenso',
    title: 'Cómo se arma el consenso',
    summary:
      'El consenso toma la temperatura del promedio de GFS y ECMWF; la lluvia, el viento y el ícono siguen a ECMWF. ECMWF es el modelo europeo y, según la verificación del propio ECMWF en 101 estaciones de Argentina (2020–2024), es el que mejor acierta temperatura y viento en el país. En una medición propia de SkyPulse (14 estaciones, un año), el promedio de los dos modelos acertó mejor la temperatura máxima que ECMWF solo; por eso la temperatura es el promedio. GFS es el modelo de EE. UU. y acierta parecido en lluvia. En Previsión, dentro de "Avanzado", podés ver cada modelo por separado para compararlos.',
    providers: ['GFS (NOAA, EE. UU.)', 'ECMWF (Europa)'],
  },
  {
    id: 'ahora',
    title: 'El tiempo de ahora',
    summary:
      'Si hay un aeropuerto cercano con un reporte METAR reciente, el "ahora" usa esa medición real para la temperatura, el viento y la humedad. Si no, usa la estimación del modelo de Open-Meteo.',
    providers: ['METAR del aeropuerto más cercano (Aviation Weather Center, NOAA)', 'Open-Meteo'],
  },
  {
    id: 'avisos',
    title: 'Avisos oficiales',
    summary:
      'Cuando el Servicio Meteorológico Nacional publica avisos que alcanzan tu ubicación, SkyPulse los muestra tal cual vienen de la fuente, sin interpretación propia y ordenados por gravedad.',
    providers: ['Servicio Meteorológico Nacional (SMN)'],
  },
  {
    id: 'herramientas',
    title: 'Secado de ropa, Hacer deporte, Lavar el auto y Cota de nieve',
    summary:
      'Usan el mismo pronóstico horario de Open-Meteo y lo convierten en un puntaje o una recomendación con cálculos propios de SkyPulse.',
    providers: ['Open-Meteo'],
  },
  {
    id: 'incendios',
    title: 'Incendios',
    summary:
      'El riesgo es una estimación de SkyPulse a partir del pronóstico horario de temperatura, humedad, viento y lluvia. Open-Meteo no trae el índice meteorológico de incendio (FWI), así que el puntaje siempre es una estimación.',
    providers: ['Open-Meteo'],
  },
  {
    id: 'niebla',
    title: 'Niebla y visibilidad',
    summary:
      'La visibilidad actual sale del METAR del aeropuerto más cercano, que es un dato medido; si no hay, se usa una estimación numérica. Las próximas 12 horas salen del TAF del aeropuerto más cercano, emitido por meteorólogos de aviación; si no hay, se estiman a partir de la humedad, el punto de rocío y el viento del pronóstico.',
    providers: ['Aviation Weather Center (NOAA)', 'Open-Meteo'],
  },
  {
    id: 'metar',
    title: 'METAR y TAF',
    summary:
      'La página de METAR y TAF consulta el METAR a través de CheckWX y muestra el TAF decodificado por período a partir de los datos del Aviation Weather Center (aviationweather.gov). Niebla y el "ahora" de Previsión también usan los del Aviation Weather Center.',
    providers: ['CheckWX', 'Aviation Weather Center (NOAA)'],
  },
  {
    id: 'aeronautica',
    title: 'Altitud de densidad y Cizalladura',
    summary:
      'Son cálculos propios de SkyPulse a partir de los valores que cargás. En Cizalladura, el viento puede precargarse desde el METAR del aeropuerto más cercano.',
    providers: ['Aviation Weather Center (NOAA), solo para precargar el viento en Cizalladura'],
  },
  {
    id: 'terremotos',
    title: 'Terremotos',
    summary:
      'La fuente principal es el Centro Sismológico Europeo (EMSC), que incluye la red NSNA/INPRES de Argentina con menor latencia. Si el EMSC no devuelve eventos, se consulta la red sísmica global del USGS. Los datos se guardan unos 5 minutos antes de volver a consultarse.',
    providers: ['EMSC (Europa)', 'USGS (EE. UU.)'],
  },
  {
    id: 'volcanes',
    title: 'Volcanes',
    summary:
      'El Observatorio Argentino de Vigilancia Volcánica (OAVV, del SEGEMAR) no publica una API: el nivel de alerta se lee del indicador de color que publica el observatorio. Si no se puede leer, el volcán figura "sin datos" en lugar de mostrar un nivel inventado. Los datos se guardan 2 horas antes de volver a consultarse.',
    providers: ['OAVV · SEGEMAR'],
  },
  {
    id: 'explicativas',
    title: 'Radar, Nubes, Lluvias y Desastres',
    summary:
      'Son páginas explicativas escritas por SkyPulse: no muestran datos en vivo. Los enlaces de Desastres llevan a sitios de organismos oficiales, como USGS, EMSC, NOAA o el SMN.',
    providers: [],
  },
  {
    id: 'informativo',
    title: 'Informativo, no oficial',
    summary:
      'Los pronósticos y las estimaciones de SkyPulse son informativos y no son avisos oficiales. Para alertas y decisiones importantes, seguí la consulta oficial en smn.gob.ar.',
    providers: [],
  },
]
