const SECTIONS: { title: string; body: string }[] = [
  {
    title: 'Qué datos recolectamos',
    body: 'SkyPulse no tiene registro de usuarios ni formularios que pidan nombre, email o teléfono. El único dato personal que puede usarse es tu ubicación geográfica (latitud/longitud), y es opcional: se pide vía el permiso de geolocalización del navegador, solo para mostrarte clima, terremotos y demás datos cerca tuyo. Podés rechazar el permiso y buscar tu ciudad manualmente.',
  },
  {
    title: 'Dónde se guarda tu ubicación',
    body: 'La última ubicación que elegiste se guarda en el almacenamiento local de tu navegador (localStorage), únicamente en tu dispositivo. Nunca se envía a un servidor propio ni se comparte con terceros — solo se usa para consultar las APIs meteorológicas y sísmicas con esas coordenadas.',
  },
  {
    title: 'Cookies y analítica',
    body: 'Usamos Google Tag Manager y Vercel Analytics para entender cómo se usa el sitio (páginas visitadas, básicamente). Estas herramientas solo se activan si aceptás el banner de cookies que aparece en tu primera visita. Podés rechazarlo y seguir usando SkyPulse sin ninguna limitación — tu elección se recuerda en tu navegador.',
  },
  {
    title: 'Servicios externos que consultamos',
    body: 'Los datos meteorológicos y sísmicos que mostramos vienen de fuentes públicas: SMN, USGS, EMSC, Open-Meteo y Windy. Consultamos esas APIs con las coordenadas que elegiste, pero no les enviamos ningún otro dato tuyo.',
  },
  {
    title: 'Tus opciones',
    body: 'Podés borrar la ubicación guardada y las cookies de analítica en cualquier momento desde la configuración de tu navegador. Al hacerlo, SkyPulse vuelve a pedirte el permiso de ubicación y a mostrar el banner de cookies en tu próxima visita.',
  },
]

export function Privacidad() {
  return (
    <div className="max-w-2xl mx-auto py-8 space-y-6">
      <h1
        className="text-2xl"
        style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
      >
        Política de privacidad
      </h1>
      <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
        SkyPulse es una herramienta de consulta meteorológica y sísmica sin registro de usuarios. Esta página explica, en criollo, qué datos tocamos y para qué.
      </p>

      {SECTIONS.map(s => (
        <section key={s.title} className="space-y-1.5">
          <h2 className="text-sm font-semibold" style={{ color: 'var(--color-foreground)' }}>
            {s.title}
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
            {s.body}
          </p>
        </section>
      ))}
    </div>
  )
}
