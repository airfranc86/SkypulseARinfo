/**
 * WeatherIcon — renders Meteocons animated SVGs as inline React components.
 *
 * Uses vite-plugin-svgr (?react suffix) so CSS keyframe animations embedded
 * in each SVG file work in the browser (they would be silently stripped in
 * <img> tags due to browser security restrictions).
 */
import type { SVGProps } from 'react'

import ClearDay            from '@/assets/meteocons/clear-day.svg?react'
import ClearNight          from '@/assets/meteocons/clear-night.svg?react'
import PartlyCloudyDay     from '@/assets/meteocons/partly-cloudy-day.svg?react'
import PartlyCloudyNight   from '@/assets/meteocons/partly-cloudy-night.svg?react'
import OvercastDay         from '@/assets/meteocons/overcast-day.svg?react'
import OvercastNight       from '@/assets/meteocons/overcast-night.svg?react'
import FogDay              from '@/assets/meteocons/fog-day.svg?react'
import FogNight            from '@/assets/meteocons/fog-night.svg?react'
import Drizzle             from '@/assets/meteocons/drizzle.svg?react'
import PartlyCloudyDayDrizzle   from '@/assets/meteocons/partly-cloudy-day-drizzle.svg?react'
import PartlyCloudyNightDrizzle from '@/assets/meteocons/partly-cloudy-night-drizzle.svg?react'
import Rain                from '@/assets/meteocons/rain.svg?react'
import PartlyCloudyDayRain   from '@/assets/meteocons/partly-cloudy-day-rain.svg?react'
import PartlyCloudyNightRain from '@/assets/meteocons/partly-cloudy-night-rain.svg?react'
import Snow                from '@/assets/meteocons/snow.svg?react'
import PartlyCloudyDaySnow   from '@/assets/meteocons/partly-cloudy-day-snow.svg?react'
import PartlyCloudyNightSnow from '@/assets/meteocons/partly-cloudy-night-snow.svg?react'
import Sleet               from '@/assets/meteocons/sleet.svg?react'
import Thunderstorms       from '@/assets/meteocons/thunderstorms.svg?react'
import ThunderstormsDay    from '@/assets/meteocons/thunderstorms-day.svg?react'
import ThunderstormsNight  from '@/assets/meteocons/thunderstorms-night.svg?react'
import Thermometer         from '@/assets/meteocons/thermometer.svg?react'
import Humidity            from '@/assets/meteocons/humidity.svg?react'
import Wind                from '@/assets/meteocons/wind.svg?react'
import UvIndex             from '@/assets/meteocons/uv-index.svg?react'
import Sunrise             from '@/assets/meteocons/sunrise.svg?react'
import Sunset              from '@/assets/meteocons/sunset.svg?react'
import MoonNew             from '@/assets/meteocons/moon-new.svg?react'
import MoonWaxingCrescent  from '@/assets/meteocons/moon-waxing-crescent.svg?react'
import MoonFirstQuarter    from '@/assets/meteocons/moon-first-quarter.svg?react'
import MoonWaxingGibbous   from '@/assets/meteocons/moon-waxing-gibbous.svg?react'
import MoonFull            from '@/assets/meteocons/moon-full.svg?react'
import MoonWaningGibbous   from '@/assets/meteocons/moon-waning-gibbous.svg?react'
import MoonLastQuarter     from '@/assets/meteocons/moon-last-quarter.svg?react'
import MoonWaningCrescent  from '@/assets/meteocons/moon-waning-crescent.svg?react'

type SvgComponent = React.FC<SVGProps<SVGSVGElement>>

const ICON_MAP: Record<string, SvgComponent> = {
  'clear-day':                    ClearDay,
  'clear-night':                  ClearNight,
  'partly-cloudy-day':            PartlyCloudyDay,
  'partly-cloudy-night':          PartlyCloudyNight,
  'overcast-day':                 OvercastDay,
  'overcast-night':               OvercastNight,
  'fog-day':                      FogDay,
  'fog-night':                    FogNight,
  'drizzle':                      Drizzle,
  'partly-cloudy-day-drizzle':    PartlyCloudyDayDrizzle,
  'partly-cloudy-night-drizzle':  PartlyCloudyNightDrizzle,
  'rain':                         Rain,
  'partly-cloudy-day-rain':       PartlyCloudyDayRain,
  'partly-cloudy-night-rain':     PartlyCloudyNightRain,
  'snow':                         Snow,
  'partly-cloudy-day-snow':       PartlyCloudyDaySnow,
  'partly-cloudy-night-snow':     PartlyCloudyNightSnow,
  'sleet':                        Sleet,
  'thunderstorms':                Thunderstorms,
  'thunderstorms-day':            ThunderstormsDay,
  'thunderstorms-night':          ThunderstormsNight,
  'thermometer':                  Thermometer,
  'humidity':                     Humidity,
  'wind':                         Wind,
  'uv-index':                     UvIndex,
  'sunrise':                      Sunrise,
  'sunset':                       Sunset,
  'moon-new':                     MoonNew,
  'moon-waxing-crescent':         MoonWaxingCrescent,
  'moon-first-quarter':           MoonFirstQuarter,
  'moon-waxing-gibbous':          MoonWaxingGibbous,
  'moon-full':                    MoonFull,
  'moon-waning-gibbous':          MoonWaningGibbous,
  'moon-last-quarter':            MoonLastQuarter,
  'moon-waning-crescent':         MoonWaningCrescent,
}

interface WeatherIconProps {
  /** Icon code returned by the backend (e.g. "clear-day", "partly-cloudy-night-rain") */
  code: string
  size?: number
  className?: string
  /** Used only as fallback when code is unknown — defaults to true (day) */
  isDay?: boolean
}

export function WeatherIcon({ code, size = 48, className, isDay = true }: WeatherIconProps) {
  const IconComponent = ICON_MAP[code] ?? (isDay ? ClearDay : ClearNight)

  return (
    <IconComponent
      width={size}
      height={size}
      className={className}
      aria-hidden="true"
      style={{ display: 'block', flexShrink: 0 }}
    />
  )
}
