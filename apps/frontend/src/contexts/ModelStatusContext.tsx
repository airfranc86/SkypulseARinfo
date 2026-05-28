import {
  createContext,
  useReducer,
  useEffect,
  type ReactNode,
  type Dispatch,
} from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

export type ModelCategory = 'weather' | 'forecast' | 'earthquakes'

export type ModelState = {
  source: string | null
  active: boolean
  updatedAt: number | null
}

export type ModelStatusState = Record<ModelCategory, ModelState>

export type ModelStatusAction =
  | { type: 'SET_SOURCE'; category: ModelCategory; source: string }
  | { type: 'SET_ERROR'; category: ModelCategory }

// ── Initial state ─────────────────────────────────────────────────────────────

const INITIAL: ModelStatusState = {
  weather:     { source: null, active: false, updatedAt: null },
  forecast:    { source: null, active: false, updatedAt: null },
  earthquakes: { source: null, active: false, updatedAt: null },
}

const SESSION_KEY = 'skypulse:model-status'

function isModelStatusState(v: unknown): v is ModelStatusState {
  if (typeof v !== 'object' || v === null) return false
  const categories: ModelCategory[] = ['weather', 'forecast', 'earthquakes']
  return categories.every(cat => {
    const entry = (v as Record<string, unknown>)[cat]
    return (
      typeof entry === 'object' &&
      entry !== null &&
      'source' in entry &&
      'active' in entry &&
      'updatedAt' in entry
    )
  })
}

function loadFromSession(): ModelStatusState {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return INITIAL
    const parsed: unknown = JSON.parse(raw)
    return isModelStatusState(parsed) ? parsed : INITIAL
  } catch {
    return INITIAL
  }
}

// ── Reducer ───────────────────────────────────────────────────────────────────

function reducer(state: ModelStatusState, action: ModelStatusAction): ModelStatusState {
  switch (action.type) {
    case 'SET_SOURCE': {
      const next: ModelStatusState = {
        ...state,
        [action.category]: {
          source: action.source,
          active: true,
          updatedAt: Date.now(),
        },
      }
      return next
    }
    case 'SET_ERROR': {
      const next: ModelStatusState = {
        ...state,
        [action.category]: {
          source: 'error',
          active: false,
          updatedAt: Date.now(),
        },
      }
      return next
    }
    default:
      return state
  }
}

// ── Contexts ──────────────────────────────────────────────────────────────────

export const ModelStatusContext = createContext<ModelStatusState | null>(null)
export const ModelStatusDispatchContext = createContext<Dispatch<ModelStatusAction> | null>(null)

// ── Provider ──────────────────────────────────────────────────────────────────

export function ModelStatusProvider({ children }: { children: ReactNode }) {
  const [status, dispatch] = useReducer(reducer, undefined, loadFromSession)

  // Persist to sessionStorage on every state change
  useEffect(() => {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(status))
    } catch {
      // sessionStorage not available — silently ignore
    }
  }, [status])

  return (
    <ModelStatusContext.Provider value={status}>
      <ModelStatusDispatchContext.Provider value={dispatch}>
        {children}
      </ModelStatusDispatchContext.Provider>
    </ModelStatusContext.Provider>
  )
}

