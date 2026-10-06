/**
 * The one list of SkyPulse tools: route, menu label, card copy, icon, landing group, look and color.
 * The menu pills (both rows), the landing cards and the decision shortcuts all read from here
 * (the shortcuts through `NAV_PILL_COLORS`), so a tool looks the same everywhere.
 * Colors are only defined in this file.
 *
 * Two looks:
 * - `legacy` (the 8 top-row tools): the colors and presence they had before, kept as approved.
 * - `layer` (the 8 bottom-row tools): "Estratos", approved by the user on 2026-10-06. The color says at
 *   what height the phenomenon lives, and a four-step staircase marks the same layer without color.
 *   No violet, lilac, magenta or pink; red and amber stay for severity only.
 */
import {
  Activity, Car, Cloud, CloudRain, CloudSun, Eye, Gauge, Mountain, MountainSnow, Radar, Radio,
  Shirt, TreePine, TriangleAlert, Waves, WindArrowDown, type LucideIcon,
} from 'lucide-react'
import type { PillColors, PillLook } from './navContrast.ts'

// ── Layers ("Estratos") ──────────────────────────────────────────────────────

export type LayerId = 'ground' | 'low' | 'clouds' | 'space'

/** 0 is the ground, 3 is space: the lit step of the staircase and of the card altimeter. */
export type LayerLevel = 0 | 1 | 2 | 3

export interface Layer {
  level: LayerLevel
  /** Shown on the landing card tag. */
  name: string
  /** `accent`: tint, border, icon and the fill of the current pill. `label`: the light text tone. */
  colors: PillColors
}

export const LAYERS: Record<LayerId, Layer> = {
  ground: { level: 0, name: 'Al ras del suelo', colors: { accent: '#cbb9a0', label: '#efe7da' } },
  low: { level: 1, name: 'Capa baja', colors: { accent: '#6fd3b0', label: '#d4f6ea' } },
  clouds: { level: 2, name: 'Donde nacen las nubes', colors: { accent: '#7db9f2', label: '#dcebfc' } },
  space: { level: 3, name: 'Desde el espacio', colors: { accent: '#d5e4f2', label: '#f3f8fc' } },
}

/** Text and icon color on a filled (current page) layer pill. */
export const LAYER_INK = '#071225'

// ── Landing groups ───────────────────────────────────────────────────────────

export type ToolFamilyId = 'decide' | 'risks' | 'sky' | 'aeronautics'

export interface ToolFamily {
  id: ToolFamilyId
  /** Group heading on the landing. */
  title: string
}

/** Group headings on the landing: the brand gold at 85 %, the same as "¿Qué querés hacer hoy?". */
export const GROUP_HEADING = { color: '#c8a84b', alpha: 'd9' } as const

// ── Tools ────────────────────────────────────────────────────────────────────

interface ToolBase {
  id: string
  path: string
  /** Short name on the menu pill (also its accessible name). */
  label: string
  /** Card heading on the landing. */
  title: string
  /** Card text on the landing: plain words, no model or source names. */
  description: string
  Icon: LucideIcon
  family: ToolFamilyId
  /** Pill and card colors; for a layer tool, the colors of its layer. */
  colors: PillColors
}

export type Tool = ToolBase & ({ look: Extract<PillLook, 'legacy'>; layer?: undefined } | { look: Extract<PillLook, 'layer'>; layer: LayerId })

type ToolCopy = Omit<ToolBase, 'colors'>

const legacy = (tool: ToolCopy, colors: PillColors): Tool => ({ ...tool, look: 'legacy', colors })
const onLayer = (tool: ToolCopy, layer: LayerId): Tool => ({ ...tool, look: 'layer', layer, colors: LAYERS[layer].colors })

const FAMILIES = {
  decide: { id: 'decide', title: 'Para decidir hoy' },
  risks: { id: 'risks', title: 'Riesgos' },
  sky: { id: 'sky', title: 'Cielo' },
  aeronautics: { id: 'aeronautics', title: 'Aeronáutica' },
} as const satisfies Record<ToolFamilyId, ToolFamily>

const DECIDE_TOOLS: readonly Tool[] = [
  legacy({
    id: 'forecast', path: '/prevision', label: 'Previsión', title: 'Previsión del clima',
    description: 'Temperatura, viento y lluvia para los próximos 7 días.', Icon: CloudSun, family: 'decide',
  }, { accent: '#c8a84b', label: '#937e3e' }),
  legacy({
    id: 'sport', path: '/hacer-deporte', label: 'Hacer deporte', title: 'Hacer deporte',
    description: '¿Las condiciones acompañan? UV, humedad, viento y sensación térmica.', Icon: Activity, family: 'decide',
  }, { accent: '#3fb8c4', label: '#308c98' }),
  legacy({
    id: 'laundry', path: '/tender-ropa', label: 'Secado de ropa', title: 'Secado de ropa',
    description: 'Los mejores días para tender según lluvia, viento y humedad.', Icon: Shirt, family: 'decide',
  }, { accent: '#3ecf7a', label: '#2e985f' }),
  legacy({
    id: 'carwash', path: '/lavar-auto', label: 'Lavar el auto', title: 'Lavar el auto',
    description: 'El día ideal de la semana para lavar sin que la lluvia lo arruine.', Icon: Car, family: 'decide',
  }, { accent: '#5aaad8', label: '#4686ad' }),
  legacy({
    id: 'snow-line', path: '/cota-de-nieve', label: 'Cota de nieve', title: 'Cota de nieve',
    description: '¿Hasta qué altura llega la nieve en la cordillera hoy?', Icon: MountainSnow, family: 'decide',
  }, { accent: '#90aabb', label: '#6d8392' }),
]

const RISK_TOOLS: readonly Tool[] = [
  legacy({
    id: 'earthquakes', path: '/terremotos', label: 'Terremotos', title: 'Terremotos',
    description: 'Sismos recientes cerca tuyo, con magnitud y distancia en tiempo real.', Icon: Waves, family: 'risks',
  }, { accent: '#e05545', label: '#c46057' }),
  legacy({
    id: 'volcanoes', path: '/volcanes', label: 'Volcanes', title: 'Volcanes',
    description: 'Estado de alerta de los principales volcanes del país.', Icon: Mountain, family: 'risks',
  }, { accent: '#e05545', label: '#c46057' }),
  legacy({
    id: 'fires', path: '/incendios', label: 'Incendios', title: 'Incendios',
    description: 'Riesgo de incendio forestal según temperatura, viento y humedad.', Icon: TreePine, family: 'risks',
  }, { accent: '#f0a030', label: '#ae762a' }),
  onLayer({
    id: 'disasters', path: '/desastres', label: 'Desastres', title: 'Desastres naturales',
    description: '7 fenómenos globales: datos históricos, fuentes y qué hacer.', Icon: TriangleAlert, family: 'risks',
  }, 'ground'),
]

const SKY_TOOLS: readonly Tool[] = [
  onLayer({
    id: 'clouds', path: '/nubes', label: 'Nubes', title: 'Catálogo del cielo',
    description: '13 tipos de nubes y 5 fenómenos aeronáuticos con escalas de peligro.', Icon: Cloud, family: 'sky',
  }, 'clouds'),
  onLayer({
    id: 'rain', path: '/lluvias', label: 'Lluvias', title: 'Lluvias según las nubes',
    description: 'Qué lluvia esperar según el tipo de nube en el cielo.', Icon: CloudRain, family: 'sky',
  }, 'clouds'),
  onLayer({
    id: 'radar', path: '/radar', label: 'Radar', title: 'Radar y satélite',
    description: 'Cómo interpretar colores de radar e imágenes satelitales IR.', Icon: Radar, family: 'sky',
  }, 'space'),
  onLayer({
    id: 'fog', path: '/niebla', label: 'Niebla', title: 'Niebla y visibilidad',
    description: 'Visibilidad actual y pronóstico de niebla hora a hora.', Icon: Eye, family: 'sky',
  }, 'ground'),
]

/**
 * Aeronautics, kept as its own list so the whole family can move to a separate section:
 * drop it from `TOOL_FAMILIES` and from the catalog row below, and nothing else names it.
 * Each tool carries its own layer, so the block keeps its colors wherever it goes.
 */
export const AERONAUTICS_TOOLS: readonly Tool[] = [
  onLayer({
    id: 'metar', path: '/metar', label: 'METAR', title: 'METAR & TAF',
    description: 'Reporte meteorológico real de cualquier aeródromo del mundo.', Icon: Radio, family: 'aeronautics',
  }, 'low'),
  onLayer({
    id: 'density-altitude', path: '/altitud-de-densidad', label: 'Altitud de densidad', title: 'Altitud de densidad',
    description: 'Qué le hace el aire de hoy a tu velamen y a la aeronave de salto.', Icon: Gauge, family: 'aeronautics',
  }, 'low'),
  onLayer({
    id: 'wind-shear', path: '/cizalladura', label: 'Cizalladura / LLWS', title: 'Cizalladura del viento',
    description: 'Qué tan brusco cambia el viento entre el suelo y 1.000 ft, antes de aterrizar.', Icon: WindArrowDown, family: 'aeronautics',
  }, 'low'),
]

/** Landing groups, in order: the group heading, then its cards. */
export const TOOL_FAMILIES: readonly { family: ToolFamily; tools: readonly Tool[] }[] = [
  { family: FAMILIES.decide, tools: DECIDE_TOOLS },
  { family: FAMILIES.risks, tools: RISK_TOOLS },
  { family: FAMILIES.sky, tools: SKY_TOOLS },
  { family: FAMILIES.aeronautics, tools: AERONAUTICS_TOOLS },
]

export const TOOLS: readonly Tool[] = TOOL_FAMILIES.flatMap((group) => group.tools)

const BY_ID = new Map(TOOLS.map((tool) => [tool.id, tool]))
const BY_PATH = new Map(TOOLS.map((tool) => [tool.path, tool]))

export type NavRowId = 'tools' | 'catalog'

/** Menu rows by tool id: live-data tools on top, reference pages below. */
const NAV_ROWS: Record<NavRowId, readonly string[]> = {
  tools: ['forecast', 'sport', 'laundry', 'carwash', 'earthquakes', 'snow-line', 'volcanoes', 'fires'],
  catalog: ['clouds', ...AERONAUTICS_TOOLS.map((tool) => tool.id), 'disasters', 'rain', 'radar', 'fog'],
}

function toolById(id: string): Tool {
  const tool = BY_ID.get(id)
  if (!tool) throw new Error(`Herramienta desconocida en el menú: ${id}`)
  return tool
}

/** The tools of one menu row, in display order. */
export function navRow(row: NavRowId): Tool[] {
  return NAV_ROWS[row].map(toolById)
}

export function toolByPath(path: string): Tool | undefined {
  return BY_PATH.get(path)
}
