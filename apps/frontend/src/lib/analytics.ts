export function pushEvent(eventName: string, params: Record<string, unknown> = {}): void {
  window.dataLayer = window.dataLayer || []
  window.dataLayer.push({
    event: eventName,
    ...params,
  })
}
