import { WeatherIcon } from '@/components/ui/WeatherIcon'
import type { DailyEntry } from '@/lib/api'
import { confidenceColor } from '@/lib/confidence'

interface Props {
  days: DailyEntry[]
}

export function Forecast7dTable({ days }: Props) {
  return (
    <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid var(--color-border)' }}>
      <table className="w-full text-sm border-collapse" style={{ minWidth: '560px' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--color-border)', background: 'rgba(200,168,75,0.04)' }}>
            {['Día', 'Tiempo', 'Máx', 'Mín', 'Lluvia%', 'Viento', 'Cota nieve', 'Fiabilidad'].map((h) => (
              <th
                key={h}
                className="text-left px-4 py-2.5 font-medium text-xs"
                style={{ color: 'var(--color-muted-foreground)' }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {days.map((day, i) => {
            const confColor = confidenceColor(day.confidence_label)
            return (
              <tr
                key={day.date}
                style={{
                  borderBottom: i < days.length - 1 ? '1px solid var(--color-border)' : 'none',
                }}
              >
                <td className="px-4 py-3">
                  <p className="font-medium capitalize" style={{ color: 'var(--color-foreground)' }}>
                    {day.day_label}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                    {day.day_label_long}
                  </p>
                </td>
                <td className="px-4 py-3">
                  <WeatherIcon code={day.icon} size={28} />
                </td>
                <td className="px-4 py-3 font-semibold" style={{ color: 'var(--color-foreground)' }}>
                  {day.temp_max !== null ? `${Math.round(day.temp_max)}°C` : '—'}
                </td>
                <td className="px-4 py-3" style={{ color: 'var(--color-muted-foreground)' }}>
                  {day.temp_min !== null ? `${Math.round(day.temp_min)}°C` : '—'}
                </td>
                <td className="px-4 py-3" style={{ color: 'var(--color-info)' }}>
                  {day.precip_prob !== null ? `${Math.round(day.precip_prob)}%` : '—'}
                </td>
                <td className="px-4 py-3" style={{ color: 'var(--color-muted-foreground)' }}>
                  {day.wind_speed_max !== null ? `${Math.round(day.wind_speed_max)} km/h` : '—'}
                </td>
                <td className="px-4 py-3" style={{ color: 'var(--color-muted-foreground)' }}>
                  {day.snow_level_m !== null ? `${Math.round(day.snow_level_m).toLocaleString('es-AR')} m` : '—'}
                </td>
                <td className="px-4 py-3">
                  <span
                    className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                    style={{ background: `${confColor}18`, color: confColor }}
                  >
                    {day.confidence_label}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
