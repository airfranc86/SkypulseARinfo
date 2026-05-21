import clearDay from '@/assets/meteocons/clear-day.svg?url'
import clearNight from '@/assets/meteocons/clear-night.svg?url'
import partlyCloudyDay from '@/assets/meteocons/partly-cloudy-day.svg?url'
import partlyCloudyNight from '@/assets/meteocons/partly-cloudy-night.svg?url'
import overcastDay from '@/assets/meteocons/overcast-day.svg?url'
import overcastNight from '@/assets/meteocons/overcast-night.svg?url'
import fogDay from '@/assets/meteocons/fog-day.svg?url'
import fogNight from '@/assets/meteocons/fog-night.svg?url'
import drizzle from '@/assets/meteocons/drizzle.svg?url'
import partlyCloudyDayDrizzle from '@/assets/meteocons/partly-cloudy-day-drizzle.svg?url'
import partlyCloudyNightDrizzle from '@/assets/meteocons/partly-cloudy-night-drizzle.svg?url'
import rain from '@/assets/meteocons/rain.svg?url'
import partlyCloudyDayRain from '@/assets/meteocons/partly-cloudy-day-rain.svg?url'
import partlyCloudyNightRain from '@/assets/meteocons/partly-cloudy-night-rain.svg?url'
import snow from '@/assets/meteocons/snow.svg?url'
import partlyCloudyDaySnow from '@/assets/meteocons/partly-cloudy-day-snow.svg?url'
import partlyCloudyNightSnow from '@/assets/meteocons/partly-cloudy-night-snow.svg?url'
import sleet from '@/assets/meteocons/sleet.svg?url'
import thunderstorms from '@/assets/meteocons/thunderstorms.svg?url'
import thunderstormsDay from '@/assets/meteocons/thunderstorms-day.svg?url'
import thunderstormsNight from '@/assets/meteocons/thunderstorms-night.svg?url'
import thermometer from '@/assets/meteocons/thermometer.svg?url'
import humidity from '@/assets/meteocons/humidity.svg?url'
import wind from '@/assets/meteocons/wind.svg?url'
import uvIndex from '@/assets/meteocons/uv-index.svg?url'
import sunrise from '@/assets/meteocons/sunrise.svg?url'
import sunset from '@/assets/meteocons/sunset.svg?url'
import moonNew from '@/assets/meteocons/moon-new.svg?url'
import moonWaxingCrescent from '@/assets/meteocons/moon-waxing-crescent.svg?url'
import moonFirstQuarter from '@/assets/meteocons/moon-first-quarter.svg?url'
import moonWaxingGibbous from '@/assets/meteocons/moon-waxing-gibbous.svg?url'
import moonFull from '@/assets/meteocons/moon-full.svg?url'
import moonWaningGibbous from '@/assets/meteocons/moon-waning-gibbous.svg?url'
import moonLastQuarter from '@/assets/meteocons/moon-last-quarter.svg?url'
import moonWaningCrescent from '@/assets/meteocons/moon-waning-crescent.svg?url'

const ICON_MAP: Record<string, string> = {
  'clear-day': clearDay,
  'clear-night': clearNight,
  'partly-cloudy-day': partlyCloudyDay,
  'partly-cloudy-night': partlyCloudyNight,
  'overcast-day': overcastDay,
  'overcast-night': overcastNight,
  'fog-day': fogDay,
  'fog-night': fogNight,
  'drizzle': drizzle,
  'partly-cloudy-day-drizzle': partlyCloudyDayDrizzle,
  'partly-cloudy-night-drizzle': partlyCloudyNightDrizzle,
  'rain': rain,
  'partly-cloudy-day-rain': partlyCloudyDayRain,
  'partly-cloudy-night-rain': partlyCloudyNightRain,
  'snow': snow,
  'partly-cloudy-day-snow': partlyCloudyDaySnow,
  'partly-cloudy-night-snow': partlyCloudyNightSnow,
  'sleet': sleet,
  'thunderstorms': thunderstorms,
  'thunderstorms-day': thunderstormsDay,
  'thunderstorms-night': thunderstormsNight,
  'thermometer': thermometer,
  'humidity': humidity,
  'wind': wind,
  'uv-index': uvIndex,
  'sunrise': sunrise,
  'sunset': sunset,
  'moon-new': moonNew,
  'moon-waxing-crescent': moonWaxingCrescent,
  'moon-first-quarter': moonFirstQuarter,
  'moon-waxing-gibbous': moonWaxingGibbous,
  'moon-full': moonFull,
  'moon-waning-gibbous': moonWaningGibbous,
  'moon-last-quarter': moonLastQuarter,
  'moon-waning-crescent': moonWaningCrescent,
}

interface WeatherIconProps {
  /** Icon code returned by the backend (e.g. "clear-day", "partly-cloudy-night-rain") */
  code: string
  size?: number
  alt?: string
  className?: string
}

export function WeatherIcon({ code, size = 48, alt = '', className }: WeatherIconProps) {
  const src = ICON_MAP[code] ?? ICON_MAP['clear-day']

  return (
    <img
      src={src}
      alt={alt || code}
      width={size}
      height={size}
      className={className}
      style={{ display: 'block', flexShrink: 0 }}
      draggable={false}
    />
  )
}
