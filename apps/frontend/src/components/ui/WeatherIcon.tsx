/**
 * WeatherIcon — renders Meteocons animated SVGs as inline React components.
 *
 * Uses vite-plugin-svgr (?react suffix) so CSS keyframe animations embedded
 * in each SVG file work in the browser (they would be silently stripped in
 * <img> tags due to browser security restrictions).
 */
import { useEffect, useLayoutEffect, useRef, useState, type SVGProps } from 'react'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { glowFilter } from '@/lib/iconGlow'
import { ICON_VIEW_MARGIN, iconMotion } from '@/lib/iconMotion'
import { isWeatherIconCode, type WeatherIconCode } from '@/lib/weatherIconCodes'

import ClearDay            from '@/assets/meteocons/clear-day.svg?react'
import ClearNight          from '@/assets/meteocons/clear-night.svg?react'
import PartlyCloudyDay     from '@/assets/meteocons/partly-cloudy-day.svg?react'
import PartlyCloudyNight   from '@/assets/meteocons/partly-cloudy-night.svg?react'
import Overcast            from '@/assets/meteocons/overcast.svg?react'
import OvercastDay         from '@/assets/meteocons/overcast-day.svg?react'
import OvercastNight       from '@/assets/meteocons/overcast-night.svg?react'
import Fog                 from '@/assets/meteocons/fog.svg?react'
import FogDay              from '@/assets/meteocons/fog-day.svg?react'
import FogNight            from '@/assets/meteocons/fog-night.svg?react'
import Drizzle             from '@/assets/meteocons/drizzle.svg?react'
import OvercastDrizzle     from '@/assets/meteocons/overcast-drizzle.svg?react'
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
import Hail                from '@/assets/meteocons/hail.svg?react'
import MostlyClearDay            from '@/assets/meteocons/mostly-clear-day.svg?react'
import MostlyClearNight          from '@/assets/meteocons/mostly-clear-night.svg?react'
import MostlyClearDayRain        from '@/assets/meteocons/mostly-clear-day-rain.svg?react'
import MostlyClearNightRain      from '@/assets/meteocons/mostly-clear-night-rain.svg?react'
import MostlyClearDaySnow        from '@/assets/meteocons/mostly-clear-day-snow.svg?react'
import MostlyClearNightSnow      from '@/assets/meteocons/mostly-clear-night-snow.svg?react'
import ThunderstormsMostlyClearDay       from '@/assets/meteocons/thunderstorms-mostly-clear-day.svg?react'
import ThunderstormsMostlyClearNight     from '@/assets/meteocons/thunderstorms-mostly-clear-night.svg?react'
import ThunderstormsMostlyClearDayHail   from '@/assets/meteocons/thunderstorms-mostly-clear-day-hail.svg?react'
import ThunderstormsMostlyClearNightHail from '@/assets/meteocons/thunderstorms-mostly-clear-night-hail.svg?react'
import ThunderstormsDayHail      from '@/assets/meteocons/thunderstorms-day-hail.svg?react'
import ThunderstormsNightHail    from '@/assets/meteocons/thunderstorms-night-hail.svg?react'
import ThunderstormsOvercastHail from '@/assets/meteocons/thunderstorms-overcast-hail.svg?react'
import Thermometer         from '@/assets/meteocons/thermometer.svg?react'
import Humidity            from '@/assets/meteocons/humidity.svg?react'
import Wind                from '@/assets/meteocons/wind.svg?react'
import WindBeaufort5       from '@/assets/meteocons/wind-beaufort-5.svg?react'
import WindBeaufort6       from '@/assets/meteocons/wind-beaufort-6.svg?react'
import WindBeaufort7       from '@/assets/meteocons/wind-beaufort-7.svg?react'
import WindBeaufort8       from '@/assets/meteocons/wind-beaufort-8.svg?react'
import WindBeaufort9       from '@/assets/meteocons/wind-beaufort-9.svg?react'
import WindBeaufort10      from '@/assets/meteocons/wind-beaufort-10.svg?react'
import WindBeaufort11      from '@/assets/meteocons/wind-beaufort-11.svg?react'
import WindBeaufort12      from '@/assets/meteocons/wind-beaufort-12.svg?react'
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

const ICON_MAP: Record<WeatherIconCode, SvgComponent> = {
  'clear-day':                    ClearDay,
  'clear-night':                  ClearNight,
  'partly-cloudy-day':            PartlyCloudyDay,
  'partly-cloudy-night':          PartlyCloudyNight,
  'overcast':                     Overcast,
  'overcast-day':                 OvercastDay,
  'overcast-night':               OvercastNight,
  'fog':                          Fog,
  'fog-day':                      FogDay,
  'fog-night':                    FogNight,
  'drizzle':                      Drizzle,
  'overcast-drizzle':             OvercastDrizzle,
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
  'hail':                         Hail,
  'mostly-clear-day':             MostlyClearDay,
  'mostly-clear-night':           MostlyClearNight,
  'mostly-clear-day-rain':        MostlyClearDayRain,
  'mostly-clear-night-rain':      MostlyClearNightRain,
  'mostly-clear-day-snow':        MostlyClearDaySnow,
  'mostly-clear-night-snow':      MostlyClearNightSnow,
  'thunderstorms-mostly-clear-day':        ThunderstormsMostlyClearDay,
  'thunderstorms-mostly-clear-night':      ThunderstormsMostlyClearNight,
  'thunderstorms-mostly-clear-day-hail':   ThunderstormsMostlyClearDayHail,
  'thunderstorms-mostly-clear-night-hail': ThunderstormsMostlyClearNightHail,
  'thunderstorms-day-hail':       ThunderstormsDayHail,
  'thunderstorms-night-hail':     ThunderstormsNightHail,
  'thunderstorms-overcast-hail':  ThunderstormsOvercastHail,
  'thermometer':                  Thermometer,
  'humidity':                     Humidity,
  'wind':                         Wind,
  'wind-beaufort-5':              WindBeaufort5,
  'wind-beaufort-6':              WindBeaufort6,
  'wind-beaufort-7':              WindBeaufort7,
  'wind-beaufort-8':              WindBeaufort8,
  'wind-beaufort-9':              WindBeaufort9,
  'wind-beaufort-10':             WindBeaufort10,
  'wind-beaufort-11':             WindBeaufort11,
  'wind-beaufort-12':             WindBeaufort12,
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
  /** Adds a soft drop-shadow glow tinted to match the phenomenon (sun=gold, moon=lavender, precip=info blue). Off by default — opt in for hero/featured placements. */
  glow?: boolean
  /** Texto alternativo. Con label el ícono se anuncia como imagen; sin él es decorativo (aria-hidden). */
  label?: string
}

/**
 * Cuadro (en segundos) en el que se congela el ícono con movimiento reducido. A t = 0 las gotas de
 * lluvia y los copos están en opacidad 0; a 0,45 s hay dos a mitad de caída.
 */
const REST_FRAME_S = 0.45

/** One IntersectionObserver shared by every icon on the page, instead of one per icon. */
const inViewListeners = new WeakMap<Element, (inView: boolean) => void>()
let sharedObserver: IntersectionObserver | null = null

function observeInView(element: Element, onChange: (inView: boolean) => void): () => void {
  if (typeof IntersectionObserver === 'undefined') return () => {}
  sharedObserver ??= new IntersectionObserver(
    (entries) => {
      for (const entry of entries) inViewListeners.get(entry.target)?.(entry.isIntersecting)
    },
    { rootMargin: ICON_VIEW_MARGIN },
  )
  inViewListeners.set(element, onChange)
  sharedObserver.observe(element)
  return () => {
    sharedObserver?.unobserve(element)
    inViewListeners.delete(element)
  }
}

export function WeatherIcon({ code, size = 48, className, isDay = true, glow = false, label }: WeatherIconProps) {
  const IconComponent = isWeatherIconCode(code) ? ICON_MAP[code] : isDay ? ClearDay : ClearNight
  const svgRef = useRef<SVGSVGElement>(null)
  const reducedMotion = useReducedMotion()
  // Visible until the observer says otherwise (also where IntersectionObserver does not exist).
  const [inView, setInView] = useState(true)
  const a11y: SVGProps<SVGSVGElement> = label
    ? { role: 'img', 'aria-label': label }
    : { 'aria-hidden': true }

  // Every running SMIL timeline costs style and layout work on each frame, even off screen or
  // inside a collapsed section (FRA-342): the icon only animates while it can be seen.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    return observeInView(svg, setInView)
  }, [IconComponent])

  // Los Meteocons animan con SMIL, que ignora prefers-reduced-motion: se pausan en un cuadro
  // donde el fenómeno (gotas, copos, rayo) se ve. Al volver a permitir movimiento, se reanudan.
  // Fuera de pantalla se pausan donde estén, sin saltar de cuadro.
  useLayoutEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const motion = iconMotion({ reducedMotion, inView })
    if (motion === 'freeze') {
      svg.setCurrentTime(REST_FRAME_S)
      svg.pauseAnimations()
    } else if (motion === 'pause') {
      svg.pauseAnimations()
    } else {
      svg.unpauseAnimations()
    }
  }, [reducedMotion, inView, IconComponent])

  return (
    <IconComponent
      ref={svgRef}
      width={size}
      height={size}
      className={className}
      {...a11y}
      style={{ display: 'block', flexShrink: 0, filter: glow ? glowFilter(code) : undefined }}
    />
  )
}
