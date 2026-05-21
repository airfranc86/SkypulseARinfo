import { type ReactElement } from 'react'

interface IndexGaugeProps {
  value: number
  label: string
  size?: number
}

function getColor(value: number): string {
  if (value < 40) return 'oklch(0.627 0.258 29.23)'
  if (value <= 70) return 'oklch(0.795 0.184 86.05)'
  return 'oklch(0.723 0.219 142.50)'
}

export function IndexGauge({ value, label, size = 180 }: IndexGaugeProps): ReactElement {
  const R = 70
  const circumference = Math.PI * R
  const clampedValue = Math.max(0, Math.min(100, value))
  const fillLength = circumference * (clampedValue / 100)
  const color = getColor(clampedValue)
  const width = size
  const height = size * 0.6

  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 200 120"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Track */}
      <path
        d="M 30 100 A 70 70 0 0 1 170 100"
        fill="none"
        stroke="var(--color-muted)"
        strokeWidth={12}
        strokeLinecap="round"
      />
      {/* Fill */}
      <path
        d="M 30 100 A 70 70 0 0 1 170 100"
        fill="none"
        stroke={color}
        strokeWidth={12}
        strokeLinecap="round"
        strokeDasharray={`${fillLength} ${circumference}`}
      />
      {/* Valor del índice */}
      <text
        x={100}
        y={88}
        fontSize={36}
        fontWeight={700}
        textAnchor="middle"
        fill={color}
      >
        {clampedValue}
      </text>
      {/* Label text */}
      <text
        x={100}
        y={108}
        fontSize={11}
        textAnchor="middle"
        fill="var(--color-muted-foreground)"
      >
        {label}
      </text>
    </svg>
  )
}
