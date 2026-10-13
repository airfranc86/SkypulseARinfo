/**
 * Assistant (Mora) configuration read from the build environment. It is pure: the env comes in as a
 * parameter (the caller passes `import.meta.env`), so `node --test` covers it without touching Vite. Same
 * pattern as `lib/alertas/config.ts`.
 *
 * Environment variable:
 *
 * - `VITE_ASISTENTE_VISIBLE`: shows Mora only when it is exactly the text `true`. Any other value (`TRUE`,
 *   `1`, `true ` with a trailing space, empty) or a missing variable keeps her hidden: the assistant is off
 *   by default. Set it in Vercel (the frontend build); it is the only assistant variable that goes there.
 *   There is no tracked `.env.example`, which is why it is documented here.
 *
 * The AI model keys NEVER get the `VITE_` prefix: Vite would bundle them into the public JavaScript. They
 * live only in the backend (Render) and, locally, in the developer's own `.env`.
 *
 * No component reads this yet: the module only gets the flag reading ready.
 */

/** Name of the environment variable that turns the assistant on. */
export const VARIABLE_ASISTENTE_VISIBLE = 'VITE_ASISTENTE_VISIBLE'

/** The only value that turns it on. */
const VALOR_VISIBLE = 'true'

export interface ConfigAsistente {
  /** Mora is shown only with `VITE_ASISTENTE_VISIBLE === 'true'`. */
  readonly visible: boolean
}

/**
 * The assistant configuration. The flag is strict: only the exact text "true" shows it ("TRUE", "1",
 * "true " or a missing value keep it hidden). It does not throw on a missing or odd env.
 */
export function leerConfigAsistente(env: Record<string, unknown> | undefined): ConfigAsistente {
  const entorno = typeof env === 'object' && env !== null ? env : {}
  return Object.freeze({
    visible: entorno[VARIABLE_ASISTENTE_VISIBLE] === VALOR_VISIBLE,
  })
}
