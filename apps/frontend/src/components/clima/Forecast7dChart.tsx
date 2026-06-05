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
import type { DailyEntry } from '@/lib/api'

interface Props {
  days: DailyEntry[]
}

export function Forecast7dChart({ days }: Props) {
  const chartData = days.map((d) => ({
    ...d,
    label: d.day_label,
    temp_max: d.temp_max !== null ? Math.round(d.temp_max) : null,
    temp_min: d.temp_min !== null ? Math.round(d.temp_min) : null,
    precip_prob: d.precip_prob !== null ? Math.round(d.precip_prob) : null,
  }))

  return (
    <div style={{ height: '280px' }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 12, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(200,168,75,0.1)" vertical={false} />

          <XAxis
            dataKey="label"
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
            fill="rgba(90,170,216,0.25)"
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
  )
}
