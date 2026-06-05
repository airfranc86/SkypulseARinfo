/**
 * WindArrow — flecha SVG que rota según la dirección meteorológica del viento.
 * Datos en convención FROM (estándar meteorológico): deg=0 → viento DEL Norte.
 * La flecha muestra la dirección TO (+180°): deg=0 → apunta al Sur (hacia donde va).
 */
interface Props {
  deg: number
  size?: number
  color?: string
}

export function WindArrow({ deg, size = 16, color = 'currentColor' }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      style={{
        transform: `rotate(${deg + 180}deg)`,
        transition: 'transform 0.4s ease',
        display: 'inline-block',
        flexShrink: 0,
      }}
    >
      {/* Cuerpo de la flecha + punta */}
      <path d="M12 2 L7 13 L10.5 13 L10.5 22 L13.5 22 L13.5 13 L17 13 Z" fill={color} />
    </svg>
  )
}
