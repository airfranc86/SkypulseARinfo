import { useState } from 'react'
import { Mascota, type TamanoMora } from '@/components/asistente/Mascota'
import { useParpadeo } from '@/hooks/useParpadeo'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { HUMORES, type HumorMora } from '@/lib/asistente/humor'
import type { ParpadeoMora } from '@/lib/asistente/programarParpadeo'

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

const TAMANOS: readonly TamanoMora[] = [24, 44, 64, 96]

/** When each mood shows up (the rules live in lib/asistente/humor.ts; the panel moods are set by the panel). */
const CUANDO: Record<HumorMora, string> = {
  alerta: 'Hay un aviso naranja o rojo del SMN, o riesgo de tormenta alto.',
  pensando: 'El panel espera la respuesta.',
  respondiendo: 'El panel está escribiendo la respuesta.',
  confundido: 'El panel no pudo responder.',
  dormido: 'Es de noche.',
  erizado: 'Ráfagas de 40 km/h o más, o viento intenso.',
  encogido: 'Está lloviendo (1 mm o más).',
  planeando: 'De día, con térmicas y sin tormenta.',
  reposo: 'El resto del tiempo.',
}

function BotonPrueba({ children, onClick, disabled }: { children: string; onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`min-h-11 rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-medium transition-colors hover:bg-[var(--color-muted)] motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`}
    >
      {children}
    </button>
  )
}

/** Mora with her own blink loop (the one the floating bubble will use), on a light and on a dark background. */
function MoraEnVivo() {
  const { parpadeo, alTerminarParpadeo } = useParpadeo(false)
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="rounded-xl bg-[var(--color-muted)] p-4">
        <Mascota tamano={96} parpadeo={parpadeo} alTerminarParpadeo={alTerminarParpadeo} />
      </div>
      <div className="rounded-xl bg-slate-900 p-4">
        <Mascota tamano={96} parpadeo={parpadeo} alTerminarParpadeo={alTerminarParpadeo} />
      </div>
    </div>
  )
}

export function Preguntale() {
  const movimientoReducido = useReducedMotion()
  const [parpadeo, setParpadeo] = useState<ParpadeoMora>(0)
  // With reduced motion the CSS plays no animation (so no `animationend`), and clicking while a blink plays would not
  // restart it: in both cases the buttons wait instead of leaving the page stuck on a blink that never ends.
  const bloqueado = movimientoReducido || parpadeo !== 0
  const parpadear = (veces: 1 | 2) => setParpadeo(veces)
  const alTerminar = () => setParpadeo(0)

  return (
    <div className="space-y-10">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold">Preguntale a Mora</h1>
        <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
          Página de revisión de la mascota. Solo existe con la bandera del asistente encendida y no tiene enlace en el menú.
        </p>
      </header>

      <section aria-labelledby="mora-tamanos" className="space-y-4">
        <h2 id="mora-tamanos" className="text-lg font-semibold">
          Tamaños
        </h2>
        <div className="flex flex-wrap items-end gap-6">
          {TAMANOS.map((tamano) => (
            <figure key={tamano} className="flex flex-col items-center gap-2">
              <Mascota tamano={tamano} parpadeo={parpadeo} alTerminarParpadeo={alTerminar} />
              <figcaption className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                {tamano} px
              </figcaption>
            </figure>
          ))}
        </div>
        <div className="flex flex-wrap gap-3">
          <BotonPrueba onClick={() => parpadear(1)} disabled={bloqueado}>
            Parpadear
          </BotonPrueba>
          <BotonPrueba onClick={() => parpadear(2)} disabled={bloqueado}>
            Parpadear dos veces
          </BotonPrueba>
        </div>
      </section>

      <section aria-labelledby="mora-en-vivo" className="space-y-4">
        <h2 id="mora-en-vivo" className="text-lg font-semibold">
          En vivo (parpadea sola)
        </h2>
        <MoraEnVivo />
      </section>

      <section aria-labelledby="mora-estados" className="space-y-4">
        <h2 id="mora-estados" className="text-lg font-semibold">
          Los nueve estados
        </h2>
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {HUMORES.map((humor) => (
            <li key={humor} className="flex items-center gap-4 rounded-xl border border-[var(--color-border)] p-4">
              <Mascota estado={humor} tamano={96} />
              <div className="space-y-1">
                <p className="font-medium">{humor}</p>
                <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
                  {CUANDO[humor]}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
