import { useState } from 'react'
import { FadeContent } from '@/components/animated/FadeContent'
import { Dither } from '@/components/animated/Dither'

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

const RADAR_SCALE = [
  { color: '#4ade80', label: 'Verde claro',              mmh: '< 5 mm/h',   desc: 'Lluvia ligera — menos de 5 mm/h. Paraguas alcanza. Sin riesgo de vuelo.' },
  { color: '#a3e635', label: 'Verde intenso / amarillo', mmh: '5–20 mm/h',  desc: 'Lluvia moderada — 5 a 20 mm/h. Se moja fácil. Vuelo VFR empieza a ser incómodo.' },
  { color: '#facc15', label: 'Amarillo',                 mmh: '20–35 mm/h', desc: 'Lluvia moderada a intensa — 20 a 35 mm/h. Visibilidad reducida. Evitar salir a volar.' },
  { color: '#f97316', label: 'Naranja',                  mmh: '35–50 mm/h', desc: 'Lluvia intensa — 35 a 50 mm/h. Posibles ráfagas y rayos. Riesgo real en tierra y en vuelo.' },
  { color: '#ef4444', label: 'Rojo',                     mmh: '> 50 mm/h',  desc: 'Lluvia muy intensa o granizo — más de 50 mm/h. Tormentas severas. No salir.' },
  { color: '#a855f7', label: 'Morado / violeta',         mmh: 'Granizo',    desc: 'Granizo grande confirmado o reflectividad extrema. Núcleo severo de tormenta. Peligro máximo.', highlight: true },
]

const SAT_SCALE = [
  { tone: '#ffffff', label: 'Blanco brillante',    alt: '≥ 12 km',   altColor: '#ef4444', desc: 'Nubes muy altas y frías: cumulonimbos, yunques. Tormentas activas. Alta probabilidad de lluvia fuerte, granizo y rayos.' },
  { tone: '#d4d4d4', label: 'Gris claro',          alt: '5–8 km',    altColor: '#94a3b8', desc: 'Nubes medias: altostratos, altocúmulos. Lluvia posible pero no severa. Sin peligro inminente.' },
  { tone: '#737373', label: 'Gris medio / oscuro', alt: '1–3 km',    altColor: '#94a3b8', desc: 'Nubes bajas: estratos, estratocúmulos. Cielo cubierto, llovizna posible. Sin tormenta.' },
  { tone: '#1a1a2e', label: 'Negro / muy oscuro',  alt: 'Despejado', altColor: '#4ade80', desc: 'Cielo despejado o superficie terrestre. Sin nubes en ese punto. Temperatura alta.' },
]

const EXERCISES = [
  {
    tag: 'Caso 1 — Radar', tagColor: '#f97316',
    question: <>El radar muestra una mancha <strong style={{ color: '#f1f5f9' }}>naranja-roja</strong> con un núcleo morado en el centro, moviéndose hacia tu ciudad. Velocidad estimada: 40 km/h. Llegada: 30 minutos.</>,
    answerTag: 'Interpretación', answerColor: '#ef4444',
    answer: <>Tormenta severa en camino. El naranja indica lluvia muy intensa; el núcleo morado confirma <strong style={{ color: '#f1f5f9' }}>granizo probable</strong>. Tenés unos 30 minutos para buscar refugio sólido. Suspendé cualquier actividad al aire libre y posponé cualquier vuelo sin excepción. No esperes a que llegue para actuar.</>,
  },
  {
    tag: 'Caso 2 — Satélite IR', tagColor: '#7dd3fc',
    question: <>El satélite infrarrojo muestra una espiral de <strong style={{ color: '#f1f5f9' }}>blanco brillante</strong> con un ojo oscuro en el centro, sobre el Atlántico, a 400 km de la costa. El sistema tiene 600 km de diámetro.</>,
    answerTag: 'Interpretación', answerColor: '#7dd3fc',
    answer: <>Sistema tropical bien organizado — probablemente <strong style={{ color: '#f1f5f9' }}>huracán o tormenta tropical</strong>. El blanco brillante en espiral indica nubes muy altas y frías con convección intensa. El ojo oscuro confirma estructura ciclónica definida. Consultá el NHC o SMN para trayectoria: a 400 km puede impactar en 12–24 horas según la velocidad de traslación.</>,
  },
  {
    tag: 'Caso 3 — Radar + Satélite', tagColor: '#4ade80',
    question: <>El radar muestra manchas <strong style={{ color: '#f1f5f9' }}>verde claro dispersas</strong> en la zona. El satélite IR muestra <strong style={{ color: '#f1f5f9' }}>gris suave</strong> sin ningún blanco brillante. Temperatura en tierra: 18 °C.</>,
    answerTag: 'Interpretación', answerColor: '#4ade80',
    answer: <>Situación tranquila. El verde claro en el radar indica <strong style={{ color: '#f1f5f9' }}>llovizna o lluvia ligera</strong>, no tormenta. El gris suave en IR confirma que las nubes son bajas y débiles — sin desarrollo convectivo. Un día gris y húmedo, posiblemente con llovizna intermitente. Paraguas útil, sin riesgo de tormenta ni granizo. Vuelo VFR posible con revisión de visibilidad.</>,
  },
]

const REC_CARDS = [
  { color: '#a855f7', emoji: '🟣', title: 'Morado en radar',        desc: 'Granizo grande confirmado. Buscá refugio sólido inmediatamente. Protegé vehículos. Prohibición total de vuelo. No salgas hasta que el color desaparezca del radar.' },
  { color: '#e2e8f0', emoji: '⬜', title: 'Blanco en satélite IR',  desc: 'Inestabilidad activa con nubes muy altas. Controlá el radar en paralelo. Si el blanco crece y se organiza, hay tormenta en desarrollo. Posponer actividades al aire libre.' },
  { color: '#4ade80', emoji: '🟢', title: 'Verde claro + gris suave', desc: 'Situación tranquila. Lluvia ligera posible, sin tormenta ni granizo. Paraguas suficiente. Vuelo VFR viable con revisión de visibilidad en el aeródromo.' },
]

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ExerciseCard({ tag, tagColor, question, answerTag, answerColor, answer }: typeof EXERCISES[number]) {
  const [open, setOpen] = useState(false)
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <button
        type="button"
        className="w-full text-left flex items-start justify-between gap-4 px-5 py-4"
        onClick={() => setOpen(v => !v)}
      >
        <div>
          <p className="text-[.63rem] font-medium tracking-widest uppercase mb-1" style={{ color: tagColor }}>{tag}</p>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-foreground)' }}>{question}</p>
        </div>
        <span
          className="shrink-0 mt-0.5 text-base transition-transform"
          style={{
            color: 'var(--color-muted-foreground)',
            transform: open ? 'rotate(45deg)' : 'none',
          }}
        >＋</span>
      </button>
      {open && (
        <div className="px-5 pb-5 border-t" style={{ borderColor: 'var(--color-border)', background: 'rgba(0,0,0,.15)' }}>
          <p className="text-[.63rem] font-medium tracking-widest uppercase mt-4 mb-2" style={{ color: answerColor }}>{answerTag}</p>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>{answer}</p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Radar() {
  return (
    <div className="relative">
      <Dither opacity={0.03} />

      <FadeContent>
        {/* Header */}
        <div className="mb-10 text-center">
          <p className="text-[.62rem] font-medium tracking-[.28em] uppercase mb-4" style={{ color: '#c8a84b' }}>
            Leer el cielo digital
          </p>
          <h1
            className="text-4xl sm:text-5xl font-semibold leading-tight mb-4"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Radar y satélite{' '}
            <em style={{ color: '#c8a84b', fontStyle: 'italic' }}>en lenguaje simple</em>
          </h1>
          <p className="text-sm max-w-lg mx-auto leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
            No hace falta ser meteorólogo para leer un radar o una imagen satelital. Dos herramientas, un idioma.
          </p>
        </div>

        <div className="space-y-12">

          {/* 1. Intro */}
          <section>
            <h2 className="text-xl font-semibold italic mb-5" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}>
              ¿Qué mide cada uno?
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[
                { accent: '#4ade80', title: 'Radar meteorológico', body: <>Emite pulsos de microondas y mide la energía que <strong style={{ color: 'var(--color-foreground)' }}>rebotan las gotas de lluvia</strong> al recibirse de vuelta. Cuanto más intensa la reflexión, más agua hay en el aire. Ve lo que está pasando <em>ahora mismo</em>.</> },
                { accent: '#7dd3fc', title: 'Satélite meteorológico', body: <>Fotografía las nubes desde 36 000 km de altura. En modo <strong style={{ color: 'var(--color-foreground)' }}>infrarrojo (IR)</strong> mide la temperatura de la cima de las nubes: las más frías y brillantes son las más altas — y suelen ser las más peligrosas.</> },
              ].map(({ accent, title, body }) => (
                <div key={title} className="rounded-xl p-5" style={{ background: `${accent}08`, border: `1px solid ${accent}25` }}>
                  <p className="text-[.63rem] font-medium tracking-widest uppercase mb-2" style={{ color: accent }}>{title}</p>
                  <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>{body}</p>
                </div>
              ))}
            </div>
          </section>

          {/* 2. Radar scale */}
          <section>
            <h2 className="text-xl font-semibold italic mb-1" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}>
              La escala de colores del radar
            </h2>
            <p className="text-xs mb-5" style={{ color: 'var(--color-muted-foreground)' }}>
              Del color más tenue al más intenso — la regla es simple: <strong style={{ color: 'var(--color-foreground)' }}>más saturado = más peligroso</strong>.
            </p>
            <div className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--color-border)' }}>
              {RADAR_SCALE.map((row, i) => (
                <div
                  key={row.color}
                  className="flex items-center gap-4 px-4 py-3 border-b last:border-0"
                  style={{
                    borderColor: 'var(--color-border)',
                    background: row.highlight ? 'rgba(168,85,247,.04)' : i % 2 === 0 ? 'var(--color-card)' : 'transparent',
                  }}
                >
                  <div className="w-8 h-8 rounded shrink-0" style={{ background: row.color }} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium mb-0.5" style={{ color: 'var(--color-foreground)' }}>{row.label}</p>
                    <p className="text-[.72rem]" style={{ color: 'var(--color-muted-foreground)' }}>{row.desc}</p>
                  </div>
                  <span className="text-[.7rem] shrink-0 hidden sm:block" style={{ color: row.highlight ? '#ef4444' : 'var(--color-muted-foreground)' }}>
                    {row.mmh}
                  </span>
                </div>
              ))}
            </div>
            {/* Gradient bar */}
            <div className="mt-3 rounded-md h-3 overflow-hidden" style={{ background: 'linear-gradient(to right, #4ade80, #a3e635, #facc15, #f97316, #ef4444, #a855f7)' }} />
            <div className="flex justify-between text-[.62rem] mt-1 px-0.5" style={{ color: 'var(--color-muted-foreground)' }}>
              <span>Sin riesgo</span><span>Riesgo moderado</span><span>Peligro máximo</span>
            </div>
          </section>

          {/* 3. Satellite IR */}
          <section>
            <h2 className="text-xl font-semibold italic mb-1" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}>
              Cómo leer el satélite infrarrojo
            </h2>
            <p className="text-xs mb-5" style={{ color: 'var(--color-muted-foreground)' }}>
              En el satélite IR: <strong style={{ color: 'var(--color-foreground)' }}>más blanco = nube más alta y más fría = más peligrosa</strong>. Lo negro es tierra o mar despejado.
            </p>
            <div className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--color-border)' }}>
              {SAT_SCALE.map((row, i) => (
                <div key={row.tone} className="flex items-center gap-4 px-4 py-3 border-b last:border-0" style={{ borderColor: 'var(--color-border)', background: i % 2 === 0 ? 'var(--color-card)' : 'transparent' }}>
                  <div className="w-8 h-8 rounded shrink-0 border" style={{ background: row.tone, borderColor: 'rgba(255,255,255,.1)' }} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium mb-0.5" style={{ color: 'var(--color-foreground)' }}>{row.label}</p>
                    <p className="text-[.72rem]" style={{ color: 'var(--color-muted-foreground)' }}>{row.desc}</p>
                  </div>
                  <span className="text-[.7rem] shrink-0 hidden sm:block font-medium" style={{ color: row.altColor }}>{row.alt}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-md h-3 overflow-hidden" style={{ background: 'linear-gradient(to right, #111827, #6b7280, #d1d5db, #ffffff)' }} />
            <div className="flex justify-between text-[.62rem] mt-1 px-0.5" style={{ color: 'var(--color-muted-foreground)' }}>
              <span>Despejado</span><span>Nubes bajas</span><span>Nubes altas / peligro</span>
            </div>
          </section>

          {/* 4. Exercises */}
          <section>
            <h2 className="text-xl font-semibold italic mb-1" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}>
              ¿Qué ves en este escenario?
            </h2>
            <p className="text-xs mb-5" style={{ color: 'var(--color-muted-foreground)' }}>
              Leé cada caso y hacé clic para ver la interpretación.
            </p>
            <div className="space-y-3">
              {EXERCISES.map(ex => <ExerciseCard key={ex.tag} {...ex} />)}
            </div>
          </section>

          {/* 5. Recommendations */}
          <section>
            <h2 className="text-xl font-semibold italic mb-5" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}>
              Qué hacer según lo que ves
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {REC_CARDS.map(({ color, emoji, title, desc }) => (
                <div key={title} className="rounded-xl p-5 text-center" style={{ background: `${color}08`, border: `1px solid ${color}25` }}>
                  <div className="text-3xl mb-3">{emoji}</div>
                  <p className="text-[.72rem] font-medium tracking-wide uppercase mb-2" style={{ color }}>{title}</p>
                  <p className="text-[.75rem] leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>{desc}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Golden rule */}
          <div className="rounded-xl p-5" style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}>
            <p className="text-[.63rem] font-medium tracking-widest uppercase mb-2" style={{ color: '#c8a84b' }}>Regla de oro</p>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
              Radar y satélite son complementarios: el radar muestra <strong style={{ color: 'var(--color-foreground)' }}>dónde llueve ahora</strong>, el satélite muestra <strong style={{ color: 'var(--color-foreground)' }}>qué están haciendo las nubes</strong>. Usados juntos dan la imagen más completa. Si el satélite muestra blanco brillante pero el radar todavía no muestra rojo, la tormenta está <em style={{ color: '#c8a84b' }}>creciendo</em> — y el rojo llega en minutos.
            </p>
          </div>

        </div>
      </FadeContent>
    </div>
  )
}
