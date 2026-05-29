import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as Sentry from '@sentry/react'
import './index.css'
import App from './App.tsx'

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN

if (SENTRY_DSN && import.meta.env.PROD) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.MODE,
    release: import.meta.env.VITE_VERCEL_GIT_COMMIT_SHA || 'unknown',
    tracePropagationTargets: [
      'localhost',
      /^https:\/\/skypulse-api-mund\.onrender\.com/,
    ],
    integrations: [
      Sentry.browserTracingIntegration(),
      Sentry.replayIntegration({
        maskAllText: true,
        blockAllMedia: true,
      }),
    ],
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0.05,
    replaysOnErrorSampleRate: 1.0,
    beforeSend(event) {
      const firstFrame = event.exception?.values?.[0]?.stacktrace?.frames?.[0]
      if (firstFrame?.filename?.includes('extensions/')) return null
      return event
    },
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Sentry.ErrorBoundary fallback={<p>Ha ocurrido un error inesperado.</p>}>
      <App />
    </Sentry.ErrorBoundary>
  </StrictMode>,
)
