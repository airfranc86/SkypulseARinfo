const CONSENT_KEY = 'skypulse:analytics-consent'
const GTM_ID = 'GTM-MBG7GFM2'

export type ConsentStatus = 'accepted' | 'rejected' | null

export function getConsent(): ConsentStatus {
  try {
    const v = localStorage.getItem(CONSENT_KEY)
    return v === 'accepted' || v === 'rejected' ? v : null
  } catch {
    return null
  }
}

export function setConsent(status: 'accepted' | 'rejected'): void {
  try {
    localStorage.setItem(CONSENT_KEY, status)
  } catch {
    // localStorage no disponible (modo privado, etc.) — el banner vuelve a aparecer la próxima visita
  }
}

/** Inyecta el script de Google Tag Manager — solo debe llamarse tras consentimiento aceptado. */
export function loadGTM(): void {
  if (document.getElementById('gtm-script')) return
  window.dataLayer = window.dataLayer || []
  window.dataLayer.push({ 'gtm.start': Date.now(), event: 'gtm.js' })
  const script = document.createElement('script')
  script.id = 'gtm-script'
  script.async = true
  script.src = `https://www.googletagmanager.com/gtm.js?id=${GTM_ID}`
  document.head.appendChild(script)
}
