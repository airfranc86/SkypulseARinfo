import { useEffect, useRef, useCallback, type ReactNode, type CSSProperties, type ReactElement } from 'react'

interface ElectricBorderProps {
  children: ReactNode
  color?: string
  speed?: number
  chaos?: number
  borderRadius?: number
  displacement?: number
  className?: string
  style?: CSSProperties
}

export function ElectricBorder({
  children,
  color = '#c09c2b',
  speed = 0.5,
  chaos = 0.1,
  borderRadius = 35,
  displacement = 60,
  className,
  style,
}: ElectricBorderProps): ReactElement {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animationRef = useRef<number>(0)
  const timeRef = useRef(0)
  const lastFrameTimeRef = useRef(0)

  const random = useCallback((x: number) => {
    return (Math.sin(x * 12.9898) * 43758.5453) % 1
  }, [])

  const noise2D = useCallback(
    (x: number, y: number) => {
      const i = Math.floor(x)
      const j = Math.floor(y)
      const fx = x - i
      const fy = y - j
      const a = random(i + j * 57)
      const b = random(i + 1 + j * 57)
      const c = random(i + (j + 1) * 57)
      const d = random(i + 1 + (j + 1) * 57)
      const ux = fx * fx * (3.0 - 2.0 * fx)
      const uy = fy * fy * (3.0 - 2.0 * fy)
      return a * (1 - ux) * (1 - uy) + b * ux * (1 - uy) + c * (1 - ux) * uy + d * ux * uy
    },
    [random]
  )

  const octavedNoise = useCallback(
    (
      x: number, octaves: number, lacunarity: number, gain: number,
      baseAmplitude: number, baseFrequency: number, time: number,
      seed: number, baseFlatness: number
    ) => {
      let y = 0
      let amplitude = baseAmplitude
      let frequency = baseFrequency
      for (let i = 0; i < octaves; i++) {
        let octaveAmplitude = amplitude
        if (i === 0) octaveAmplitude *= baseFlatness
        y += octaveAmplitude * noise2D(frequency * x + seed * 100, time * frequency * 0.3)
        frequency *= lacunarity
        amplitude *= gain
      }
      return y
    },
    [noise2D]
  )

  const getCornerPoint = useCallback(
    (cx: number, cy: number, r: number, startAngle: number, arcLength: number, progress: number) => ({
      x: cx + r * Math.cos(startAngle + progress * arcLength),
      y: cy + r * Math.sin(startAngle + progress * arcLength),
    }),
    []
  )

  const getRoundedRectPoint = useCallback(
    (t: number, left: number, top: number, w: number, h: number, r: number) => {
      const sw = w - 2 * r
      const sh = h - 2 * r
      const ca = (Math.PI * r) / 2
      const total = 2 * sw + 2 * sh + 4 * ca
      const dist = t * total
      let acc = 0

      if (dist <= acc + sw) {
        const p = (dist - acc) / sw
        return { x: left + r + p * sw, y: top }
      }
      acc += sw
      if (dist <= acc + ca) {
        return getCornerPoint(left + w - r, top + r, r, -Math.PI / 2, Math.PI / 2, (dist - acc) / ca)
      }
      acc += ca
      if (dist <= acc + sh) {
        return { x: left + w, y: top + r + ((dist - acc) / sh) * sh }
      }
      acc += sh
      if (dist <= acc + ca) {
        return getCornerPoint(left + w - r, top + h - r, r, 0, Math.PI / 2, (dist - acc) / ca)
      }
      acc += ca
      if (dist <= acc + sw) {
        const p = (dist - acc) / sw
        return { x: left + w - r - p * sw, y: top + h }
      }
      acc += sw
      if (dist <= acc + ca) {
        return getCornerPoint(left + r, top + h - r, r, Math.PI / 2, Math.PI / 2, (dist - acc) / ca)
      }
      acc += ca
      if (dist <= acc + sh) {
        const p = (dist - acc) / sh
        return { x: left, y: top + h - r - p * sh }
      }
      acc += sh
      return getCornerPoint(left + r, top + r, r, Math.PI, Math.PI / 2, (dist - acc) / ca)
    },
    [getCornerPoint]
  )

  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const OCTAVES = 10
    const LACUNARITY = 1.6
    const GAIN = 0.7
    const DISPLACEMENT = displacement
    const BORDER_OFFSET = 60

    const updateSize = () => {
      const rect = container.getBoundingClientRect()
      const width = rect.width + BORDER_OFFSET * 2
      const height = rect.height + BORDER_OFFSET * 2
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.scale(dpr, dpr)
      return { width, height }
    }

    let { width, height } = updateSize()
    let lastDpr = Math.min(window.devicePixelRatio || 1, 2)

    const draw = (currentTime: number) => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      if (dpr !== lastDpr) {
        lastDpr = dpr
        const s = updateSize()
        width = s.width
        height = s.height
      }

      const deltaTime = (currentTime - lastFrameTimeRef.current) / 1000
      timeRef.current += deltaTime * speed
      lastFrameTimeRef.current = currentTime

      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.scale(dpr, dpr)

      ctx.strokeStyle = color
      ctx.lineWidth = 1.5
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'

      const left = BORDER_OFFSET
      const top = BORDER_OFFSET
      const bw = width - 2 * BORDER_OFFSET
      const bh = height - 2 * BORDER_OFFSET
      const maxR = Math.min(bw, bh) / 2
      const r = Math.min(borderRadius, maxR)

      const approxPerimeter = 2 * (bw + bh) + 2 * Math.PI * r
      const samples = Math.floor(approxPerimeter / 2)

      ctx.beginPath()
      for (let i = 0; i <= samples; i++) {
        const progress = i / samples
        const pt = getRoundedRectPoint(progress, left, top, bw, bh, r)
        const xn = octavedNoise(progress * 8, OCTAVES, LACUNARITY, GAIN, chaos, 10, timeRef.current, 0, 0)
        const yn = octavedNoise(progress * 8, OCTAVES, LACUNARITY, GAIN, chaos, 10, timeRef.current, 1, 0)
        const dx = pt.x + xn * DISPLACEMENT
        const dy = pt.y + yn * DISPLACEMENT
        if (i === 0) ctx.moveTo(dx, dy)
        else ctx.lineTo(dx, dy)
      }
      ctx.closePath()
      ctx.stroke()

      animationRef.current = requestAnimationFrame(draw)
    }

    const ro = new ResizeObserver(() => {
      const s = updateSize()
      width = s.width
      height = s.height
    })
    ro.observe(container)

    animationRef.current = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(animationRef.current)
      ro.disconnect()
    }
  }, [color, speed, chaos, borderRadius, displacement, octavedNoise, getRoundedRectPoint])

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ position: 'relative', overflow: 'visible', isolation: 'isolate', borderRadius, ...style }}
    >
      {/* Perlin-noise canvas */}
      <div style={{
        position: 'absolute', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        pointerEvents: 'none', zIndex: 2,
      }}>
        <canvas ref={canvasRef} style={{ display: 'block' }} />
      </div>

      {/* Glow layers */}
      <div style={{ position: 'absolute', inset: 0, borderRadius, pointerEvents: 'none', zIndex: 0 }}>
        <div style={{
          position: 'absolute', inset: 0, borderRadius,
          border: `1.5px solid ${color}88`, filter: 'blur(1px)',
        }} />
        <div style={{
          position: 'absolute', inset: 0, borderRadius,
          border: `1.5px solid ${color}`, filter: 'blur(4px)',
        }} />
        <div style={{
          position: 'absolute', inset: 0, borderRadius,
          zIndex: -1, transform: 'scale(1.1)', filter: 'blur(28px)',
          opacity: 0.25,
          background: `linear-gradient(-30deg, ${color}55, transparent, ${color}33)`,
        }} />
      </div>

      {/* Content */}
      <div style={{ position: 'relative', borderRadius, zIndex: 1 }}>
        {children}
      </div>
    </div>
  )
}
