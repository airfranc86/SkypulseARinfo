import type { Ref } from 'react'
import { CircleCheck, LoaderCircle, TriangleAlert, type LucideIcon } from 'lucide-react'
import { mensajeDeEstado, mensajeDePrueba, type EstadoPrueba } from '@/lib/alertas/copy'
import type { EstadoAvisos } from '@/lib/alertas/suscripcion'

type Tono = 'ok' | 'aviso' | 'progreso'

const TONOS: Record<Tono, { Icon: LucideIcon; color: string }> = {
  ok: { Icon: CircleCheck, color: 'var(--color-safe)' },
  aviso: { Icon: TriangleAlert, color: 'var(--color-watch)' },
  progreso: { Icon: LoaderCircle, color: 'var(--color-primary)' },
}

function tonoDeEstado(estado: EstadoAvisos): Tono | null {
  switch (estado.tipo) {
    case 'activo':
      return 'ok'
    case 'pidiendo-permiso':
    case 'suscribiendo':
      return 'progreso'
    case 'sin-respuesta':
    case 'denegado':
    case 'error':
      return 'aviso'
    default:
      return null
  }
}

function tonoDePrueba(prueba: EstadoPrueba): Tono | null {
  switch (prueba.tipo) {
    case 'enviada':
      return 'ok'
    case 'enviando':
      return 'progreso'
    case 'espera':
    case 'error':
      return 'aviso'
    default:
      return null
  }
}

/** Una línea del estado: un ícono distinto por tono (la información no depende del color) y el texto. */
function Linea({ tono, texto }: { tono: Tono | null; texto: string }) {
  if (texto === '') return null
  const icono = tono === null ? null : TONOS[tono]
  return (
    <p className="flex items-start gap-2 text-sm leading-relaxed text-[var(--color-foreground)]">
      {icono && (
        <icono.Icon
          size={18}
          strokeWidth={2}
          className={`mt-0.5 shrink-0 ${tono === 'progreso' ? 'animate-spin motion-reduce:animate-none' : ''}`}
          style={{ color: icono.color }}
          aria-hidden="true"
        />
      )}
      <span>{texto}</span>
    </p>
  )
}

interface RegionEstadoProps {
  /** El id con el que los botones deshabilitados apuntan a esta región (`aria-describedby`). */
  id: string
  estado: EstadoAvisos
  /** Nombre de la ciudad con avisos activos, si hay. */
  nombreZona: string | null
  prueba: EstadoPrueba
  /** Para llevarle el foco cuando un botón desaparece (activar o desactivar). */
  regionRef?: Ref<HTMLDivElement>
}

/**
 * Lo que pasó con la activación y con la prueba. Siempre montada y con `aria-live="polite"`: el lector de
 * pantalla anuncia el texto cuando aparece o cambia, sin cortar lo que está leyendo. Puede recibir el foco
 * por código (no por tabulación) para que quien navega con teclado no se quede sin lugar.
 */
export function RegionEstado({ id, estado, nombreZona, prueba, regionRef }: RegionEstadoProps) {
  return (
    <div
      ref={regionRef}
      id={id}
      role="status"
      aria-live="polite"
      tabIndex={-1}
      className="min-h-6 space-y-1.5 focus:outline-none"
    >
      <Linea tono={tonoDeEstado(estado)} texto={mensajeDeEstado(estado, nombreZona)} />
      <Linea tono={tonoDePrueba(prueba)} texto={mensajeDePrueba(prueba)} />
    </div>
  )
}
