# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Personas en Argentina que buscan una decisión práctica y rápida frente al clima o un fenómeno natural, mayormente desde el teléfono, en movimiento o con cierta urgencia (ej. curiosidad inmediata tras sentir un sismo). No son profesionales del rubro — quieren entender "qué pasa y qué hago" en segundos, sin tecnicismos.

Un segundo perfil, más operativo: personas que necesitan interpretar reportes aeronáuticos (METAR/SPECI/TAF) traducidos a riesgo y acción concreta, sin requerir formación aeronáutica completa.

## Product Purpose

SkyPulse convierte datos meteorológicos y de desastres naturales en respuestas accionables. Dos frentes activos y complementarios (confirmado explícitamente por el usuario — no es uno u otro):

- **Dashboard cuantitativo**: 15 herramientas/guías (previsión 7 días, terremotos, METAR/TAF, volcanes, incendios, niebla, cota de nieve, tender ropa, lavar auto, hacer deporte, radar, nubes, lluvias, desastres) que agregan datos reales de SMN, GFS/ECMWF (Open-Meteo), Windy, USGS, EMSC y CheckWX.
- **Sistema narrativo por fenómeno**: tarjetas con formato fijo ("cómo se ve / qué significa / acción") por tipo de nube, fenómeno aeronáutico o desastre. Hoy vive como catálogo estático dentro de páginas del dashboard (Nubes, Desastres); la dirección declarada del proyecto es evolucionar hacia generación más dinámica (plantillas → híbrido).

Éxito = el usuario entiende su situación climática o de riesgo y sabe qué hacer, en segundos, sin conocimiento técnico previo.

## Positioning

Un solo producto argentino que cruza fuentes oficiales y técnicas dispersas (SMN, GFS, ECMWF, USGS, EMSC, CheckWX, Windy) en herramientas organizadas por decisión concreta (¿tiendo la ropa hoy?, ¿es seguro volar?, ¿este sismo es grave?), en vez de mostrar datos crudos como un panel meteorológico genérico. Ningún competidor genérico (AccuWeather, Weather Channel) hace ese cruce multi-fuente ni lo traduce a decisión + narrativa consistente por fenómeno.

## Operating Context

- Mobile-first; uso frecuente casual/nocturno (ej. desde el sillón) y uso urgente en movimiento.
- Frontend: React 19 + Vite + TanStack Query + Tailwind v4, desplegado en Vercel. Backend: FastAPI (Python) desplegado en Render, con cold start conocido tras inactividad.
- Multi-fuente con fallback: Open-Meteo y Windy comparten caché; SMN, USGS, EMSC y CheckWX tienen cada uno su propio gate/caché. Upstash Redis para contadores de cuota (plan free — la base se borra tras 14 días sin actividad).

## Capabilities and Constraints

- Cuota CheckWX limitada (198/mes) con gate y contador en Redis — ya hubo un incidente real de bypass de este gate, cerrado.
- Cold start de Render agrega latencia en el primer request tras inactividad.
- Integración WRF-SMN históricamente inestable (dependencia `h5py`) — regla del proyecto: evitar fusionar múltiples fuentes/modelos hasta estabilizar.
- Backend pensado como capa mínima: proxy de claves, rate limiting y seguridad, no lógica de negocio pesada más allá de agregación/cálculo.
- Secretos nunca expuestos en el bundle del frontend.
- Terminología de dominio: "stale" (dato servido desde caché vencido como fallback), "fail-open" (degradar sin romper ante caída de Upstash).
- Sin evidencia de uso real (tráfico, usuarios, feedback) todavía — confirmado explícitamente por el usuario. No inventar métricas de adopción ni testimonios en trabajo futuro.

## Brand Commitments

- Nombre: SkyPulse. Tagline: "Meteorología que se entiende y se usa."
- Personalidad de marca: Urgente · Precisa · Nocturna — panel de monitoreo, no red social; el diseño nunca "suaviza" la gravedad de un fenómeno real.
- El peso del diseño escala con la gravedad del evento — un M6 no puede verse igual que un M2.

## Evidence on Hand

Ninguna evidencia real de uso, testimonios o métricas de tráfico todavía (confirmado por el usuario). No fabricar casos de uso, cifras de adopción ni citas de usuarios en trabajo futuro.

## Product Principles

1. Traducir datos técnicos dispersos en una decisión concreta — nunca entregar el dato crudo sin interpretar.
2. Multi-fuente con fallback honesto: si un dato es stale o está degradado, decirlo, nunca ocultar la frescura real.
3. El peso visual y narrativo escala con la gravedad real del fenómeno.
4. Urgencia sin alarmismo — comunicar seriedad sin generar pánico innecesario.
5. Simplicidad accionable: toda salida (dashboard o tarjeta narrativa) termina en algo ejecutable, nunca en "estar atento" genérico.
