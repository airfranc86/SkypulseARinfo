import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallbackMessage: string
}

interface State {
  hasError: boolean
}

/** Boundary genérico para aislar fallas de un widget (ej. el mapa) del resto de la página. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  handleRetry = (): void => {
    this.setState({ hasError: false })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          className="rounded-xl p-4 text-sm text-center space-y-2"
          role="alert"
          style={{ border: '1px solid var(--color-border)', background: 'var(--color-card)', color: 'var(--color-muted-foreground)' }}
        >
          <p>{this.props.fallbackMessage}</p>
          <button
            type="button"
            onClick={this.handleRetry}
            className="text-xs font-medium rounded-full px-3 min-h-[32px] transition-opacity hover:opacity-80"
            style={{ background: 'rgba(224,85,69,0.1)', color: '#e05545', border: '1px solid rgba(224,85,69,0.3)' }}
          >
            Reintentar
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
