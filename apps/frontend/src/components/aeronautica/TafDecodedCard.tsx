import {
  FLIGHT_CATEGORY_STYLES,
  categoryNote,
  changeExplanation,
  changeLabel,
  cloudsText,
  formatLocalInstant,
  formatTemperature,
  formatWindow,
  hasConvectiveSigns,
  isCavok,
  visibilityText,
  weatherItems,
  windText,
  type TafDecoded,
  type TafPeriod,
  type WeatherItem,
} from '@/lib/taf'
import { WeatherIcon } from '@/components/ui/WeatherIcon'

// TAF decodificado por períodos (FRA-365). Los datos llegan ya normalizados desde GET /api/taf;
// acá solo se muestran. Las horas van en hora de Argentina y, debajo, en UTC.

const MUTED = { color: 'var(--color-muted-foreground)' } as const
const LABEL_CLASS = 'text-[.67rem] font-medium tracking-widest uppercase'

function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null
  const style = FLIGHT_CATEGORY_STYLES[category] ?? FLIGHT_CATEGORY_STYLES.UNKNOWN
  return (
    <span
      title={categoryNote(category) ?? undefined}
      className="px-2.5 py-1 rounded text-[.7rem] font-medium tracking-wide"
      style={{ color: style.color, background: style.bg, border: `1px solid ${style.border}` }}
    >
      {category}
    </span>
  )
}

function Chip({ children, color, border }: { children: React.ReactNode; color: string; border: string }) {
  return (
    <span className="px-2 py-1 rounded text-[.68rem]" style={{ color, border: `1px solid ${border}` }}>
      {children}
    </span>
  )
}

function Row({ label, children, inherited }: { label: string; children: React.ReactNode; inherited?: boolean }) {
  return (
    <div className="flex gap-3 text-[.8rem] leading-[1.6]">
      <dt className="w-24 shrink-0" style={{ ...MUTED, opacity: 0.85 }}>
        {label}
      </dt>
      <dd style={{ color: 'var(--color-foreground)' }}>
        {children}
        {inherited && (
          <span className="text-[.7rem]" style={{ ...MUTED, opacity: 0.7 }}>
            {' '}
            · sin cambios
          </span>
        )}
      </dd>
    </div>
  )
}

function WeatherList({ items }: { items: WeatherItem[] }) {
  return (
    <>
      {items.map((item, index) => (
        <span key={`${item.text}-${index}`}>
          {index > 0 && ' · '}
          <span className="inline-flex items-center gap-1 align-middle">
            {item.icons.map(icon => (
              <WeatherIcon key={icon} code={icon} size={22} />
            ))}
            {item.text}
          </span>
        </span>
      ))}
    </>
  )
}

function PeriodItem({ period }: { period: TafPeriod }) {
  const time = formatWindow(period)
  const cavok = isCavok(period)
  const weather = cavok ? [] : weatherItems(period.weather)
  const clouds = cloudsText(period.clouds)
  const inherits = (field: string) => period.inherited.includes(field)
  const explanation = changeExplanation(period)
  const completesAt = period.change === 'becoming' && period.becoming_by ? formatLocalInstant(period.becoming_by) : null

  return (
    <li
      className="rounded-md px-4 py-3 space-y-2"
      style={{ border: '1px solid var(--color-border)', background: 'rgba(2,8,16,.5)' }}
    >
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <div className="text-[.85rem] font-medium" style={{ color: 'var(--color-foreground)' }}>
            {time.local}
          </div>
          <div className="text-[.67rem]" style={{ ...MUTED, opacity: 0.75 }}>
            {time.utc} UTC
          </div>
        </div>
        <div className="flex items-center flex-wrap gap-2">
          <Chip color="#90aabb" border="rgba(96,112,128,.4)">
            {changeLabel(period)}
          </Chip>
          {hasConvectiveSigns(period) && (
            <Chip color="#e05545" border="rgba(192,57,43,.4)">
              Convección: CB, TCU o tormenta
            </Chip>
          )}
          <CategoryBadge category={period.flight_category} />
        </div>
      </div>

      {(explanation || completesAt) && (
        <p className="text-[.72rem] leading-[1.6]" style={{ ...MUTED, opacity: 0.9 }}>
          {explanation}
          {completesAt && <> Cambio completo hacia {completesAt}.</>}
        </p>
      )}

      <dl className="space-y-1">
        <Row label="Viento" inherited={inherits('wind')}>
          {windText(period.wind)}
        </Row>
        {cavok ? (
          <Row label="CAVOK">Visibilidad de 10 km o más, sin nubes significativas ni fenómenos</Row>
        ) : (
          <>
            <Row label="Visibilidad" inherited={inherits('visibility')}>
              {visibilityText(period.visibility_m, period.visibility_over)}
            </Row>
            {clouds.length > 0 && (
              <Row label="Nubes" inherited={inherits('clouds')}>
                {clouds.join(' · ')}
              </Row>
            )}
            {weather.length > 0 && <Row label="Fenómenos"><WeatherList items={weather} /></Row>}
          </>
        )}
      </dl>
    </li>
  )
}

export function TafDecodedCard({ taf }: { taf: TafDecoded }) {
  const validity = taf.valid_from && taf.valid_to ? formatWindow({ valid_from: taf.valid_from, valid_to: taf.valid_to }) : null

  return (
    <div className="space-y-3">
      <div>
        <p className={`${LABEL_CLASS} mb-1.5`} style={{ ...MUTED, opacity: 0.75 }}>
          TAF — Pronóstico decodificado
        </p>
        <p className="text-[.75rem] leading-[1.6]" style={MUTED}>
          {validity && <>Vigente {validity.local}. </>}
          {taf.issued_at && <>Emitido {formatLocalInstant(taf.issued_at)}. </>}
          Horas de Argentina; debajo de cada una, UTC.
        </p>
        {taf.temperatures.length > 0 && (
          <p className="text-[.75rem] leading-[1.6]" style={MUTED}>
            {taf.temperatures.map(formatTemperature).join(' · ')}
          </p>
        )}
      </div>

      <ol className="space-y-2">
        {taf.periods.map((period, index) => (
          <PeriodItem key={`${period.valid_from}-${index}`} period={period} />
        ))}
      </ol>

      <p className="text-[.7rem] leading-[1.6]" style={{ ...MUTED, opacity: 0.85 }}>
        La categoría (VFR, MVFR, IFR, LIFR) sale de la visibilidad y el techo de cada período con los umbrales
        de la FAA; los límites están en «Categorías de vuelo», más abajo en esta página.
      </p>

      <details>
        <summary className="cursor-pointer text-[.75rem]" style={MUTED}>
          Ver el TAF original
        </summary>
        <div
          className="mt-2 rounded-md px-5 py-4 overflow-x-auto text-[.82rem] leading-[1.8]"
          style={{ fontFamily: 'monospace', color: '#c8e6ff', background: '#020810', border: '1px solid var(--color-border)' }}
        >
          {taf.raw}
        </div>
      </details>

      <p className="text-[.67rem]" style={{ ...MUTED, opacity: 0.75 }}>
        Fuente: Aviation Weather Center (NOAA),{' '}
        <a
          href="https://aviationweather.gov"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:opacity-100 transition-opacity"
        >
          aviationweather.gov
        </a>
        .
      </p>
    </div>
  )
}
