import { useId } from 'react'
import type { HumorMora } from '@/lib/asistente/humor'
import type { ParpadeoMora } from '@/lib/asistente/programarParpadeo'
import {
  ALTO_VIEWBOX,
  ANCHO_VIEWBOX,
  BANDA_CUELLO,
  CABEZA_CARA,
  CABEZA_CASQUETE,
  CABEZA_CONTORNO,
  CABEZA_ESCUDO_DER,
  CEJA_DER,
  CEJA_IZQ,
  CORRIENTES,
  CUERPO_CONTORNO,
  CUERPO_FORMA,
  EJE_CABEZA,
  EJE_CORRIENTES,
  EJE_OJOS,
  EJE_PULSO,
  ESCLERA,
  ESCLERA_SOMBRA_DESPL,
  GOTA,
  GOTA_BRILLO,
  GOTAS,
  IRIS,
  LINEA_V_CHICA_DER,
  LINEA_V_CHICA_IZQ,
  LINEA_V_GRANDE_DER,
  LINEA_V_GRANDE_IZQ,
  MECHON_1,
  MECHON_1_SOMBRA,
  MECHON_2,
  MECHON_2_SOMBRA,
  MECHONES_EXTRA,
  PARCHES,
  PARPADO_SUPERIOR,
  PICO_BANDA_DER,
  PICO_BANDA_IZQ,
  PICO_CONTORNO,
  PICO_CRESTA,
  PICO_LINEA_DER,
  PICO_LINEA_IZQ,
  PICO_NARIZ_DER,
  PICO_NARIZ_IZQ,
  PICO_SOMBRA,
  PLUMA_CURVA,
  PLUMA_HOJA,
  PLUMA_J,
  PULSO_LENTEJA_ORO,
  PULSO_LENTEJA_OSCURA,
  PULSO_PUNTOS,
  PUPILA,
  REFLEJOS,
  VIEWBOX,
} from './moraGeometria'
import './mascota.css'

/** The sizes (in px) Mora is drawn at: 24 (a dot), 44 (the floating bubble), 64 and 96. */
export type TamanoMora = 24 | 44 | 64 | 96

export interface MascotaProps {
  /** Her mood (the nine of `HumorMora`). It only moves, hides or recolors parts of the drawing. */
  estado?: HumorMora
  /** `0` eyes open; `1` / `2` plays the CSS blink once / twice (driven by `useParpadeo`). */
  parpadeo?: ParpadeoMora
  /** Called when a blink animation ends (it fires once per eye: the hook ignores the second one). */
  alTerminarParpadeo?: () => void
  tamano?: TamanoMora
  className?: string
}

type Lado = 'izq' | 'der'

const ESPEJO_CABEZA = `translate(${EJE_CABEZA} 0) scale(-1 1)`
const ESPEJO_OJOS = `translate(${EJE_OJOS} 0) scale(-1 1)`
const ESPEJO_PULSO = `translate(${EJE_PULSO} 0) scale(-1 1)`
const ESPEJO_CORRIENTES = `translate(${EJE_CORRIENTES} 0) scale(-1 1)`

function Cuerpo() {
  return (
    <g data-parte="cuerpo" className="cuerpo">
      <path d={CUERPO_FORMA} fill="var(--mora-cuerpo)" />
      <path d={CUERPO_CONTORNO} fill="none" stroke="var(--mora-tinta)" strokeWidth={8} strokeLinejoin="round" />
      <path d={BANDA_CUELLO} fill="var(--mora-tinta)" />
    </g>
  )
}

function Pulso() {
  return (
    <g data-parte="pulso" className="pulso">
      <path d={PULSO_LENTEJA_OSCURA} fill="var(--mora-tinta)" />
      <path d={PULSO_LENTEJA_OSCURA} fill="var(--mora-tinta)" transform={ESPEJO_PULSO} />
      <polyline points={PULSO_PUNTOS} fill="none" stroke="var(--mora-tinta)" strokeWidth={19} strokeLinejoin="round" strokeLinecap="round" />
      <path d={PULSO_LENTEJA_ORO} className="oro-relleno" fill="var(--mora-oro)" />
      <path d={PULSO_LENTEJA_ORO} className="oro-relleno" fill="var(--mora-oro)" transform={ESPEJO_PULSO} />
      <polyline points={PULSO_PUNTOS} className="oro-trazo" fill="none" stroke="var(--mora-oro)" strokeWidth={8.5} strokeLinejoin="round" strokeLinecap="round" />
    </g>
  )
}

function Corrientes() {
  return (
    <g data-parte="corrientes" className="corrientes" fill="none" stroke="var(--mora-corriente)" strokeLinecap="round">
      {CORRIENTES.map((d, i) => (
        <g key={d} strokeWidth={i === 0 ? 9 : 6}>
          <path d={d} />
          <path d={d} transform={ESPEJO_CORRIENTES} />
        </g>
      ))}
    </g>
  )
}

/** Rain drops above the head (only visible in encogido). They sit outside the head group: they do not sink with it. */
function Gotas() {
  return (
    <g data-parte="gotas" className="gotas">
      {GOTAS.map(({ x, y, escala }) => (
        <g key={x} transform={`translate(${x} ${y}) scale(${escala})`}>
          <path d={GOTA} fill="var(--mora-gota)" stroke="var(--mora-tinta)" strokeWidth={6} strokeLinejoin="round" />
          <path d={GOTA_BRILLO} fill="none" stroke="var(--mora-blanco)" strokeWidth={5} strokeLinecap="round" />
        </g>
      ))}
    </g>
  )
}

/** Crown tufts (right side only) and, hidden until the wind ruffles her, the four extra ones. */
function Mechones() {
  return (
    <>
      <g data-parte="mechones-extra" className="mechones-extra">
        {MECHONES_EXTRA.map((d) => (
          <path key={d} d={d} fill="var(--mora-claro)" stroke="var(--mora-tinta)" strokeWidth={6} strokeLinejoin="round" />
        ))}
      </g>
      <g data-parte="mechones" className="mechones">
        <g stroke="var(--mora-tinta)" strokeWidth={7} strokeLinejoin="round" fill="var(--mora-claro)">
          <path d={MECHON_1} />
          <path d={MECHON_2} />
        </g>
        <path d={MECHON_1_SOMBRA} fill="var(--mora-banda)" />
        <path d={MECHON_2_SOMBRA} fill="var(--mora-banda)" />
      </g>
    </>
  )
}

function Cabeza({ uid }: { uid: string }) {
  const recorte = `${uid}-cabeza`
  const forma = `${uid}-forma-cabeza`
  return (
    <g data-parte="cabeza" className="cabeza">
      <defs>
        <clipPath id={recorte}>
          <path id={forma} d={CABEZA_CONTORNO} />
        </clipPath>
      </defs>
      <use href={`#${forma}`} fill="var(--mora-banda)" />
      <g clipPath={`url(#${recorte})`}>
        <path d={CABEZA_CARA} fill="var(--mora-cara)" />
        <path d={CABEZA_CASQUETE} fill="var(--mora-casquete)" />
        <g transform={ESPEJO_CABEZA}>
          <path d={CABEZA_CASQUETE} fill="var(--mora-casquete)" />
        </g>
        <path d={CABEZA_ESCUDO_DER} fill="var(--mora-escudo)" />
        <g fill="none" stroke="var(--mora-linea)" strokeWidth={4.3} strokeLinecap="round" strokeLinejoin="round">
          <path d={LINEA_V_GRANDE_IZQ} />
          <path d={LINEA_V_GRANDE_DER} />
          <path d={LINEA_V_CHICA_IZQ} />
          <path d={LINEA_V_CHICA_DER} />
        </g>
        <g data-parte="pluma-mejilla" fill="var(--mora-pluma)">
          <path d={PLUMA_HOJA} />
          <path d={PLUMA_CURVA} />
          <path d={PLUMA_J} />
        </g>
        <g data-parte="pluma-mejilla" fill="var(--mora-pluma)" transform={ESPEJO_CABEZA}>
          <path d={PLUMA_HOJA} />
          <path d={PLUMA_CURVA} />
          <path d={PLUMA_J} />
        </g>
        {PARCHES.map(([cx, cy, r]) => (
          <circle key={cx} data-parte="parche-ojo" cx={cx} cy={cy} r={r} fill="var(--mora-parche)" />
        ))}
      </g>
      <use href={`#${forma}`} fill="none" stroke="var(--mora-tinta)" strokeWidth={8} strokeLinejoin="round" />
    </g>
  )
}

function Ojo({ lado, uid }: { lado: Lado; uid: string }) {
  const der = lado === 'der'
  const x = (v: number): number => (der ? EJE_OJOS - v : v)
  const ex = x(ESCLERA.cx)
  const { cy, rx, ry } = ESCLERA
  const despX = der ? -ESCLERA_SOMBRA_DESPL.x : ESCLERA_SOMBRA_DESPL.x
  const ix = x(IRIS.cx)
  const px = x(PUPILA.cx)
  const [gx, gy, gr] = REFLEJOS[lado].grande
  const [cx, cyChico, cr] = REFLEJOS[lado].chico
  const esclera = `${uid}-esc-${lado}`
  const iris = `${uid}-iris-${lado}`
  const caja = { x: ex - 70, y: cy - 66, width: 140, height: 132 }
  return (
    <g data-parte="ojo" data-lado={lado} className={`ojo ojo-${lado}`}>
      <defs>
        <clipPath id={esclera}>
          <ellipse cx={ex} cy={cy} rx={rx} ry={ry} />
        </clipPath>
        <clipPath id={iris}>
          <circle cx={ix} cy={IRIS.cy} r={IRIS.rColor} />
        </clipPath>
      </defs>
      <g data-parte="esclera" clipPath={`url(#${esclera})`}>
        <rect {...caja} fill="var(--mora-esclera-sombra)" />
        <ellipse cx={ex + despX} cy={cy + ESCLERA_SOMBRA_DESPL.y} rx={rx + 2} ry={ry + 2} fill="var(--mora-blanco)" />
      </g>
      {/* the gaze is clipped to the eye by a STATIC group: a clip on the moving group would travel with it */}
      <g clipPath={`url(#${esclera})`}>
        <g data-parte="mirada" className="mirada">
          <circle cx={ix} cy={IRIS.cy} r={IRIS.rBorde} fill="var(--mora-tinta-ojo)" />
          <circle cx={ix} cy={IRIS.cy} r={IRIS.rColor} fill="var(--mora-iris)" />
          <g clipPath={`url(#${iris})`}>
            <ellipse cx={ix} cy={503} rx={60} ry={29} fill="var(--mora-iris-bajo)" />
          </g>
          <circle data-parte="pupila" className="pupila" cx={px} cy={PUPILA.cy} r={PUPILA.r} fill="var(--mora-pupila)" />
          <circle data-parte="brillo" className="brillo" cx={gx} cy={gy} r={gr} fill="var(--mora-blanco)" />
          <circle data-parte="brillo" className="brillo" cx={cx} cy={cyChico} r={cr} fill="var(--mora-blanco)" />
        </g>
      </g>
      <g clipPath={`url(#${esclera})`}>
        <g data-parte="parpado" className="parpado-bajo">
          <rect {...caja} fill="var(--mora-parche)" />
        </g>
        <g data-parte="parpado-alto" className="parpado-alto">
          <rect {...caja} fill="var(--mora-parche)" />
          <line x1={ex - 70} y1={cy + 66} x2={ex + 70} y2={cy + 66} stroke="var(--mora-tinta-ojo)" strokeWidth={6} />
        </g>
      </g>
      <ellipse cx={ex} cy={cy} rx={rx} ry={ry} fill="none" stroke="var(--mora-tinta-ojo)" strokeWidth={8} />
      <path d={PARPADO_SUPERIOR} fill="var(--mora-tinta-ojo)" transform={der ? ESPEJO_OJOS : undefined} />
      <g data-parte="ojo-cerrado" className="ojo-cerrado">
        <ellipse cx={ex} cy={cy} rx={68} ry={65} fill="var(--mora-parche)" />
        <path d={`M${ex - 48} ${cy + 6} Q${ex} ${cy + 42} ${ex + 48} ${cy + 6}`} fill="none" stroke="var(--mora-tinta-ojo)" strokeWidth={8} strokeLinecap="round" />
      </g>
    </g>
  )
}

function Ceja({ lado }: { lado: Lado }) {
  return (
    <g data-parte="ceja" data-lado={lado} className={`ceja ceja-${lado}`}>
      <path d={lado === 'izq' ? CEJA_IZQ : CEJA_DER} fill="var(--mora-ceja)" stroke="var(--mora-ceja-trazo)" strokeWidth={3.6} strokeLinejoin="round" />
    </g>
  )
}

function Pico({ uid }: { uid: string }) {
  const recorte = `${uid}-pico`
  const contorno = `${uid}-contorno-pico`
  return (
    <g data-parte="pico" className="pico">
      <defs>
        <clipPath id={recorte}>
          <path id={contorno} d={PICO_CONTORNO} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${recorte})`}>
        <rect x={570} y={440} width={270} height={215} fill="var(--mora-pico)" />
        <path d={PICO_SOMBRA} fill="var(--mora-pico-sombra)" />
        <path d={PICO_BANDA_IZQ} fill="var(--mora-pico-banda-izq)" />
        <path d={PICO_BANDA_DER} fill="var(--mora-pico-banda-der)" />
        <path d={PICO_CRESTA} fill="var(--mora-pico-cresta)" />
        <ellipse cx={696.5} cy={481} rx={10} ry={4.6} transform="rotate(-14 697 481)" fill="var(--mora-pico-brillo)" />
      </g>
      <g fill="none" stroke="var(--mora-tinta)" strokeWidth={4.5} strokeLinecap="round">
        <path d={PICO_LINEA_IZQ} />
        <path d={PICO_LINEA_DER} />
      </g>
      <path d={PICO_NARIZ_IZQ} fill="var(--mora-narina)" />
      <path d={PICO_NARIZ_DER} fill="var(--mora-narina)" />
      <use href={`#${contorno}`} fill="none" stroke="var(--mora-tinta)" strokeWidth={7} strokeLinejoin="round" />
    </g>
  )
}

/**
 * Mora, the mascot of the assistant (an Andean mountain eagle, front view, head and chest). A decorative SVG:
 * `aria-hidden`, so whoever shows it puts the accessible name on its own button or heading. The drawing is the
 * one the owner approved; `estado` only moves, hides or recolors its parts (all in mascota.css), and `parpadeo`
 * plays the CSS blink. Several Moras can share a page: the clip-path ids come from `useId`.
 */
export function Mascota({ estado = 'reposo', parpadeo = 0, alTerminarParpadeo, tamano = 96, className }: MascotaProps) {
  const uid = useId()
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={VIEWBOX}
      width={tamano}
      height={Math.round((tamano * ALTO_VIEWBOX) / ANCHO_VIEWBOX)}
      className={className ? `mora ${className}` : 'mora'}
      data-estado={estado}
      data-parpadeo={parpadeo === 0 ? undefined : parpadeo}
      aria-hidden="true"
      focusable="false"
      onAnimationEnd={(e) => {
        // only the blink closes the blink cycle: `animationend` bubbles up from any animation inside the drawing
        if (e.animationName === 'mora-parpadeo') alTerminarParpadeo?.()
      }}
    >
      <Cuerpo />
      <Corrientes />
      <g data-parte="cabeza-grupo" className="cabeza-grupo">
        <Mechones />
        <Cabeza uid={uid} />
        <Ojo lado="izq" uid={uid} />
        <Ojo lado="der" uid={uid} />
        <Ceja lado="izq" />
        <Ceja lado="der" />
        <Pico uid={uid} />
      </g>
      <Gotas />
      <Pulso />
    </svg>
  )
}
