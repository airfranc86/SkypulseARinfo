import { type CSSProperties, type ReactElement, type ReactNode } from 'react'

export interface Column<T extends object = Record<string, unknown>> {
  key: string
  header: string
  render?: (value: unknown, row: T) => ReactNode
  className?: string
  /** Inline style aplicado a <th> y <td> — necesario para anchos fijos en WebKit mobile */
  style?: CSSProperties
}

interface DataTableProps<T extends object = Record<string, unknown>> {
  columns: Column<T>[]
  data: T[]
  emptyMessage?: string
}

export function DataTable<T extends object = Record<string, unknown>>({
  columns,
  data,
  emptyMessage = 'Sin datos disponibles.',
}: DataTableProps<T>): ReactElement {
  return (
    <div
      className="overflow-hidden rounded-xl border"
      style={{ borderColor: 'var(--color-border)' }}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'color-mix(in oklch, var(--color-muted) 50%, transparent)' }}>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wide ${col.className ?? ''}`}
                  style={{ color: 'var(--color-muted-foreground)', ...col.style }}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="p-8 text-center"
                  style={{ color: 'var(--color-muted-foreground)' }}
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              data.map((row, rowIndex) => (
                <tr
                  key={rowIndex}
                  style={
                    rowIndex % 2 === 0
                      ? undefined
                      : { background: 'color-mix(in oklch, var(--color-muted) 20%, transparent)' }
                  }
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={`px-4 py-3 ${col.className ?? ''}`}
                      style={{ color: 'var(--color-foreground)', ...col.style }}
                    >
                      {col.render
                        ? col.render((row as Record<string, unknown>)[col.key], row)
                        : String((row as Record<string, unknown>)[col.key] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
