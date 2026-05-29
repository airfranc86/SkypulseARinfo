import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

export function useGTMPageView(): void {
  const location = useLocation()

  useEffect(() => {
    window.dataLayer = window.dataLayer || []
    window.dataLayer.push({
      event: 'virtual_pageview',
      page_path: location.pathname + location.search,
      page_title: document.title,
    })
  }, [location])
}
