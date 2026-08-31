interface HourlyAccessibleItem {
  hourLabel: string
  description: string
}

/**
 * Alternativa textual oculta (sr-only) para gráficos de barras horarias cuyo
 * dato real solo vive en un `title` (hover-only) o dentro de un `role="img"`.
 * No reemplaza el gráfico visual — corre en paralelo.
 */
export function HourlyAccessibleList({
  items,
  label,
}: {
  items: HourlyAccessibleItem[]
  label: string
}) {
  return (
    <ul className="sr-only" aria-label={label}>
      {items.map((item, i) => (
        <li key={i}>{item.hourLabel}: {item.description}</li>
      ))}
    </ul>
  )
}
