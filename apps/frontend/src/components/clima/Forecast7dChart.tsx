import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { weekdayShort } from '@/lib/dates'
import type { DailyEntry } from '@/lib/api'

interface Props {
  days: DailyEntry[]
}

const LEGEND = [
  { label: 'Máxima', swatch: <span className="inline-block w-4 h-0.5 rounded" style={{ background: '#f0a030' }} /> },
  {
    label: 'Mínima',
    swatch: <span className="inline-block w-4 h-0 border-t-2 border-dashed" style={{ borderColor: '#5aaad8' }} />,
  },
  {
    label: 'Prob. de lluvia',
    swatch: <span className="inline-block w-2.5 h-3 rounded-sm" style={{ background: 'rgba(90,170,216,0.6)' }} />,
  },
]

/** Lectura equivalente del gráfico para quien no lo ve: los extremos de la semana. */
function chartSummary(days: DailyEntry[]): string {
  const withMax = days.filter((d) => d.temp_max !== null)
  const withMin = days.filter((d) => d.temp_min !== null)
  const withRain = days.filter((d) => d.precip_prob !== null)
  const parts = [`Pronóstico de ${days.length} días.`]
  if (withMax.length > 0) {
    const hottest = withMax.reduce((a, b) => ((b.temp_max ?? 0) > (a.temp_max ?? 0) ? b : a))
    parts.push(`Máxima más alta: ${Math.round(hottest.temp_max ?? 0)}° el ${hottest.day_label_long}.`)
  }
  if (withMin.length > 0) {
    const coldest = withMin.reduce((a, b) => ((b.temp_min ?? 0) < (a.temp_min ?? 0) ? b : a))
    parts.push(`Mínima más baja: ${Math.round(coldest.temp_min ?? 0)}° el ${coldest.day_label_long}.`)
  }
  if (withRain.length > 0) {
    const wettest = withRain.reduce((a, b) => ((b.precip_prob ?? 0) > (a.precip_prob ?? 0) ? b : a))
    const pct = Math.round(wettest.precip_prob ?? 0)
    parts.push(
      pct > 0
        ? `Mayor probabilidad de lluvia: ${pct}% el ${wettest.day_label_long}.`
        : 'Sin probabilidad de lluvia en los próximos días.',
    )
  }
  parts.push('El detalle día por día está en la vista Tabla.')
  return parts.join(' ')
}

export function Forecast7dChart({ days }: Props) {
  const chartData = days.map((d) => ({
    ...d,
    // Tres letras: con "Hoy" y "Mañana" las etiquetas de 390 px se tocaban ("HoyMañanadom").
    label: weekdayShort(d.date),
    temp_max: d.temp_max !== null ? Math.round(d.temp_max) : null,
    temp_min: d.temp_min !== null ? Math.round(d.temp_min) : null,
    precip_prob: d.precip_prob !== null ? Math.round(d.precip_prob) : null,
  }))

  return (
    <div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 pb-3 text-xs" style={{ color: 'var(--color-muted-foreground)' }} aria-hidden="true">
        {LEGEND.map(({ label, swatch }) => (
          <li key={label} className="inline-flex items-center gap-1.5">
            {swatch}
            {label}
          </li>
        ))}
      </ul>
      {/* role="img": el SVG de recharts no es navegable con sentido, así que se anuncia el
          resumen y la vista Tabla es la alternativa con el detalle. */}
      <div role="img" aria-label={chartSummary(days)} style={{ height: '280px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            margin={{ top: 12, right: 12, left: -12, bottom: 0 }}
            accessibilityLayer={false}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(200,168,75,0.1)" vertical={false} />
  
            {/* interval 0: los siete días con rótulo. Con el automático, en 390 px el eje omitía uno. */}
            <XAxis
              dataKey="label"
              interval={0}
              tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
  
            {/* Left Y: temperature */}
            <YAxis
              yAxisId="temp"
              tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              unit="°"
            />
  
            {/* Right Y: precip probability */}
            <YAxis
              yAxisId="precip"
              orientation="right"
              domain={[0, 100]}
              tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              unit="%"
            />
  
            <Tooltip
              // El eje dice "sáb"; el tooltip, el día entero.
              labelFormatter={(label, payload) => (payload?.[0]?.payload as DailyEntry | undefined)?.day_label_long ?? label}
              contentStyle={{
                background: 'var(--color-card)',
                border: '1px solid var(--color-border)',
                borderRadius: '12px',
                fontSize: '12px',
                color: 'var(--color-foreground)',
              }}
              formatter={(value, name) => {
                const v = typeof value === 'number' ? value : 0
                const n = String(name ?? '')
                if (n === 'Lluvia%') return [`${v}%`, n] as [string, string]
                return [`${v}°C`, n] as [string, string]
              }}
            />
  
            {/* 0°C reference */}
            <ReferenceLine yAxisId="temp" y={0} stroke="rgba(90,170,216,0.3)" strokeDasharray="4 2" />
  
            {/* Precipitation bars */}
            <Bar
              yAxisId="precip"
              dataKey="precip_prob"
              name="Lluvia%"
              fill="rgba(90,170,216,0.6)"
              radius={[4, 4, 0, 0]}
            />
  
            {/* Max temperature line */}
            <Line
              yAxisId="temp"
              type="monotone"
              dataKey="temp_max"
              name="Máx"
              stroke="#f0a030"
              strokeWidth={2.5}
              dot={{ r: 3, fill: '#f0a030' }}
              activeDot={{ r: 6, fill: '#f0a030' }}
            />
  
            {/* Min temperature line */}
            <Line
              yAxisId="temp"
              type="monotone"
              dataKey="temp_min"
              name="Mín"
              stroke="#5aaad8"
              strokeWidth={2}
              strokeDasharray="5 3"
              dot={false}
              activeDot={{ r: 5, fill: '#5aaad8' }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
