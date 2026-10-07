import { useId, type ReactNode } from 'react'
import { COPY, etiquetaProbar, razonDeshabilitado, type EstadoPrueba } from '@/lib/alertas/copy'
import type { EstadoAvisos, ResultadoActivar } from '@/lib/alertas/suscripcion'

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

const BASE =
  'inline-flex min-h-11 w-full items-center justify-center rounded-lg px-5 py-2 text-center text-sm font-medium transition-colors motion-reduce:transition-none sm:w-auto'

const VARIANTES = {
  primario: 'bg-[var(--color-primary)] text-[var(--color-primary-foreground)]',
  secundario: 'border border-[var(--color-border-strong)] bg-transparent text-[var(--color-foreground)]',
} as const

interface BotonProps {
  variante: keyof typeof VARIANTES
  deshabilitado?: boolean
  /** El id del texto que explica el botón (por qué está deshabilitado o una nota). */
  descripcionId?: string
  onClick: () => void
  children: ReactNode
}

/**
 * Un botón que se deshabilita con `aria-disabled` y no con `disabled`: sigue pudiendo recibir el foco, así
 * quien navega con teclado o lector de pantalla escucha por qué no se puede usar. El clic se ignora.
 */
function Boton({ variante, deshabilitado = false, descripcionId, onClick, children }: BotonProps) {
  const estilo = deshabilitado ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer hover:opacity-90'
  return (
    <button
      type="button"
      aria-disabled={deshabilitado}
      aria-describedby={descripcionId}
      onClick={() => {
        if (!deshabilitado) onClick()
      }}
      className={`${BASE} ${VARIANTES[variante]} ${estilo} ${FOCUS_RING}`}
    >
      {children}
    </button>
  )
}

interface AccionesAvisosProps {
  estado: EstadoAvisos
  puedeActivar: ResultadoActivar
  /** Hay un paso en curso (el permiso, el alta o la baja). */
  ocupado: boolean
  prueba: EstadoPrueba
  /** Segundos que faltan para poder probar otra vez; null si se puede ya. */
  esperaProbar: number | null
  /** El id de la región de estado, que explica el botón cuando el permiso está bloqueado. */
  idEstado: string
  onActivar: () => void
  onProbar: () => void
  onDesactivar: () => void
}

function BotonesActivo({
  prueba,
  esperaProbar,
  ocupado,
  onProbar,
  onDesactivar,
}: Pick<AccionesAvisosProps, 'prueba' | 'esperaProbar' | 'ocupado' | 'onProbar' | 'onDesactivar'>) {
  const idNota = useId()
  const probando = ocupado || prueba.tipo === 'enviando' || esperaProbar !== null
  return (
    <div className="space-y-2">
      <div className="flex flex-col gap-3 sm:flex-row">
        <Boton variante="primario" deshabilitado={probando} descripcionId={idNota} onClick={onProbar}>
          {etiquetaProbar(esperaProbar)}
        </Boton>
        <Boton variante="secundario" deshabilitado={ocupado} onClick={onDesactivar}>
          {ocupado ? COPY.desactivando : COPY.desactivar}
        </Boton>
      </div>
      <p id={idNota} className="text-sm text-[var(--color-muted-foreground)]">
        {COPY.notaProbar}
      </p>
    </div>
  )
}

function BotonActivar({
  estado,
  puedeActivar,
  ocupado,
  idEstado,
  onActivar,
}: Pick<AccionesAvisosProps, 'estado' | 'puedeActivar' | 'ocupado' | 'idEstado' | 'onActivar'>) {
  const idRazon = useId()
  const deshabilitado = ocupado || !puedeActivar.habilitado
  const motivo = puedeActivar.motivo
  // Con el permiso bloqueado la región de estado ya lo explica: no se repite el mismo texto.
  const repiteElEstado = motivo === 'permiso-denegado' && estado.tipo === 'denegado'
  const razon = !ocupado && motivo !== undefined && !repiteElEstado ? razonDeshabilitado(motivo) : null
  const descripcionId = razon !== null ? idRazon : deshabilitado ? idEstado : undefined

  return (
    <div className="space-y-2">
      <Boton variante="primario" deshabilitado={deshabilitado} descripcionId={descripcionId} onClick={onActivar}>
        {ocupado ? COPY.activando : COPY.activar}
      </Boton>
      {razon !== null && (
        <p id={idRazon} className="text-sm text-[var(--color-muted-foreground)]">
          {razon}
        </p>
      )}
    </div>
  )
}

/** Los botones según el estado: "Activar avisos" mientras no hay avisos, "Probar aviso" y "Desactivar avisos" con ellos. */
export function AccionesAvisos(props: AccionesAvisosProps) {
  if (props.estado.tipo === 'activo') {
    return (
      <BotonesActivo
        prueba={props.prueba}
        esperaProbar={props.esperaProbar}
        ocupado={props.ocupado}
        onProbar={props.onProbar}
        onDesactivar={props.onDesactivar}
      />
    )
  }
  return (
    <BotonActivar
      estado={props.estado}
      puedeActivar={props.puedeActivar}
      ocupado={props.ocupado}
      idEstado={props.idEstado}
      onActivar={props.onActivar}
    />
  )
}
