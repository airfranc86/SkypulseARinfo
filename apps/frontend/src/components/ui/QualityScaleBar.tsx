import { LABEL_COLOR, type QualityLabel } from '@/lib/qualityScale'

const QUALITY_SCALE: { label: QualityLabel; color: string }[] = [
  { label: 'Excelente', color: LABEL_COLOR['Excelente'] },
  { label: 'Bueno', color: LABEL_COLOR['Bueno'] },
  { label: 'Regular', color: LABEL_COLOR['Regular'] },
  { label: 'No apto', color: LABEL_COLOR['No apto'] },
]

interface QualityScaleBarProps {
  bestLabel: string
}

export function QualityScaleBar({ bestLabel }: QualityScaleBarProps) {
  return (
    <div
      className="rounded-xl p-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <p className="text-[.55rem] uppercase tracking-widest mb-3" style={{ color: 'var(--color-muted-foreground)' }}>
        Escala de aptitud
      </p>
      <div className="flex gap-[3px] h-[10px]">
        {QUALITY_SCALE.map((q) => (
          <div
            key={q.label}
            className="flex-1 rounded-full"
            style={{ background: q.color, opacity: 0.55 }}
          />
        ))}
      </div>
      <div className="flex mt-2.5">
        {QUALITY_SCALE.map((q) => (
          <div key={q.label} className="flex-1 text-center">
            <span
              className="text-[.48rem] leading-tight block"
              style={{
                color: q.color,
                fontWeight: q.label === bestLabel ? 700 : undefined,
              }}
            >
              {q.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
