import { useRef, useState, useEffect, type ReactElement } from 'react'
import Matter from 'matter-js'

interface FallingTextProps {
  text?: string
  highlightWords?: string[]
  highlightClass?: string
  trigger?: 'auto' | 'scroll' | 'click' | 'hover'
  backgroundColor?: string
  wireframes?: boolean
  gravity?: number
  mouseConstraintStiffness?: number
  fontSize?: string
  className?: string
}

export function FallingText({
  text = '',
  highlightWords = [],
  highlightClass = 'highlighted',
  trigger = 'auto',
  backgroundColor = 'transparent',
  wireframes = false,
  gravity = 1,
  mouseConstraintStiffness = 0.2,
  fontSize = '1rem',
  className = '',
}: FallingTextProps): ReactElement {
  const containerRef = useRef<HTMLDivElement>(null)
  const textRef = useRef<HTMLDivElement>(null)
  const canvasContainerRef = useRef<HTMLDivElement>(null)
  const [effectStarted, setEffectStarted] = useState(false)

  // Render word spans
  useEffect(() => {
    if (!textRef.current) return
    const words = text.split(' ')
    textRef.current.innerHTML = words
      .map(word => {
        const isHighlighted = highlightWords.some(hw => word.startsWith(hw))
        return `<span class="falling-word ${isHighlighted ? highlightClass : ''}" style="display:inline-block;margin:0 3px;cursor:default">${word}</span>`
      })
      .join(' ')
  }, [text, highlightWords, highlightClass])

  // Trigger detection
  useEffect(() => {
    if (trigger === 'auto') { setEffectStarted(true); return }
    if (trigger === 'scroll' && containerRef.current) {
      const obs = new IntersectionObserver(
        ([entry]) => { if (entry.isIntersecting) { setEffectStarted(true); obs.disconnect() } },
        { threshold: 0.1 }
      )
      obs.observe(containerRef.current)
      return () => obs.disconnect()
    }
  }, [trigger])

  // Physics
  useEffect(() => {
    if (!effectStarted || !containerRef.current || !textRef.current || !canvasContainerRef.current) return

    const { Engine, Render, World, Bodies, Runner, Mouse, MouseConstraint, Body } = Matter

    const rect = containerRef.current.getBoundingClientRect()
    const width = rect.width
    const height = rect.height
    if (width <= 0 || height <= 0) return

    const engine = Engine.create()
    engine.world.gravity.y = gravity

    const render = Render.create({
      element: canvasContainerRef.current,
      engine,
      options: { width, height, background: backgroundColor, wireframes },
    })

    const walls = [
      Bodies.rectangle(width/2, height+25, width, 50, { isStatic:true, render:{fillStyle:'transparent'} }),
      Bodies.rectangle(-25,     height/2,  50, height, { isStatic:true, render:{fillStyle:'transparent'} }),
      Bodies.rectangle(width+25,height/2,  50, height, { isStatic:true, render:{fillStyle:'transparent'} }),
      Bodies.rectangle(width/2, -25,       width, 50,  { isStatic:true, render:{fillStyle:'transparent'} }),
    ]

    const wordSpans = Array.from(textRef.current.querySelectorAll('.falling-word')) as HTMLElement[]
    const wordBodies = wordSpans.map(elem => {
      const r = elem.getBoundingClientRect()
      const x = r.left - rect.left + r.width / 2
      const y = r.top  - rect.top  + r.height / 2
      const body = Bodies.rectangle(x, y, r.width, r.height, {
        render: { fillStyle: 'transparent' },
        restitution: 0.8, frictionAir: 0.01, friction: 0.2,
      })
      Body.setVelocity(body, { x: (Math.random()-0.5)*5, y: 0 })
      Body.setAngularVelocity(body, (Math.random()-0.5)*0.05)
      elem.style.position = 'absolute'
      return { elem, body }
    })

    const mouse = Mouse.create(containerRef.current)
    const mc = MouseConstraint.create(engine, {
      mouse,
      constraint: { stiffness: mouseConstraintStiffness, render: { visible: false } },
    })
    ;(render as unknown as { mouse: typeof mouse }).mouse = mouse

    World.add(engine.world, [...walls, mc, ...wordBodies.map(wb => wb.body)])

    const runner = Runner.create()
    Runner.run(runner, engine)
    Render.run(render)

    const animId = { id: 0 }
    const updateLoop = () => {
      wordBodies.forEach(({ body, elem }) => {
        const { x, y } = body.position
        elem.style.left = `${x}px`
        elem.style.top  = `${y}px`
        elem.style.transform = `translate(-50%,-50%) rotate(${body.angle}rad)`
      })
      animId.id = requestAnimationFrame(updateLoop)
    }
    animId.id = requestAnimationFrame(updateLoop)

    return () => {
      cancelAnimationFrame(animId.id)
      Render.stop(render)
      Runner.stop(runner)
      if (render.canvas && canvasContainerRef.current?.contains(render.canvas)) {
        canvasContainerRef.current.removeChild(render.canvas)
      }
      World.clear(engine.world, false)
      Engine.clear(engine)
    }
  }, [effectStarted, gravity, wireframes, backgroundColor, mouseConstraintStiffness])

  const handleTrigger = () => {
    if (!effectStarted && (trigger === 'click' || trigger === 'hover')) setEffectStarted(true)
  }

  return (
    <div
      ref={containerRef}
      className={className}
      onClick={trigger === 'click' ? handleTrigger : undefined}
      onMouseEnter={trigger === 'hover' ? handleTrigger : undefined}
      style={{ position: 'relative', overflow: 'hidden', width: '100%', height: '100%' }}
    >
      <div
        ref={textRef}
        style={{ fontSize, lineHeight: 1.4, position: 'relative', zIndex: 1 }}
      />
      <div
        ref={canvasContainerRef}
        style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
      />
    </div>
  )
}
