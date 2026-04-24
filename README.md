# SkyPulse (monorepo)

Panel visual meteorológico híbrido + sistema de generación de historias meteorológicas.

---

## Qué es

SkyPulse combina:

- visualización de datos meteorológicos
- interpretación simplificada
- generación de contenido narrativo basado en fenómenos naturales

No es solo un panel.

Es un sistema orientado a responder:

> qué está pasando y qué debería hacer el usuario

---

## Objetivo del sistema

Transformar datos meteorológicos en información accionable.

Esto implica:

- reducir complejidad técnica
- traducir modelos en lenguaje claro
- generar contenido consistente

---

## Módulos principales

- módulo de **historias meteorológicas** (usuario general)
- módulo **aeronáutico** (METAR / SPECI / TAF)
- módulo de **desastres naturales mundiales** (impacto global)

Todos usan el mismo concepto de salida: tarjetas breves orientadas a decisiones.

---

## Formato de salida — Historias meteorológicas

Generar contenido estructurado a partir de fenómenos como:

- nubes (principal)
- tormentas
- frentes
- cambios de presión

Cada historia debe seguir una estructura fija:

[Nombre del fenómeno]

Cómo se ve:
Descripción visual simple.

Qué significa:
Interpretación meteorológica.

Contexto:
Cuándo aparece o qué indica en evolución del clima.

Decisión:
Acción concreta para el usuario.

### Ejemplos

#### Cumulonimbos

Cómo se ve: torre vertical con base oscura  
Qué significa: tormenta eléctrica, posible granizo  
Contexto: crecimiento rápido en tardes cálidas  
Decisión: evitar exposición y anticipar lluvia fuerte  

---

#### Cirros

Cómo se ve: nubes finas tipo pluma  
Qué significa: cambio atmosférico en camino  
Contexto: suelen preceder frentes cálidos  
Decisión: prever posibles lluvias en próximas horas  

---

# Catálogo de Fenómenos — SkyPulse (v1)

Listado listo para automatización.
Cada entrada incluye:

- prompt de imagen
- contenido estructurado

Formato consistente con `CLAUDE.md`.

> Sugerido: mover este catálogo completo a `docs/catalogo-fenomenos.md` y mantener aquí solo esta explicación + 2–3 ejemplos.

---

## 1. Cumulonimbos

Prompt:
cumulonimbus cloud, towering vertical storm cloud, dark base, anvil top, dramatic sky, realistic, high detail

Cumulonimbos: Las peligrosas  

Cómo se ve:  
Torres altas con base oscura. Crecen rápido hacia arriba.  

Qué significa:  
Tormenta fuerte en desarrollo. Posible granizo o ráfagas.  

Acción:  
Buscá resguardo inmediato.  

---

## 2. Cirros

Prompt:
cirrus clouds, thin wispy high altitude clouds, soft white streaks, blue sky, realistic, high detail

Cirros: Las que avisan  

Cómo se ve:  
Nubes finas como plumas. Muy altas y livianas.  

Qué significa:  
Cambio de tiempo en camino. No hay tormenta aún.  

Acción:  
Seguí el clima en las próximas horas.  

---

## 3. Cúmulos

Prompt:
cumulus clouds, fluffy white clouds, blue sky, fair weather, soft shadows, realistic

Cúmulos: Las tranquilas  

Cómo se ve:  
Nubes blancas esponjosas. Bordes bien definidos.  

Qué significa:  
Tiempo estable y agradable. Baja probabilidad de lluvia.  

Acción:  
Podés seguir sin preocuparte.  

---

## 4. Estratos

Prompt:
stratus clouds, gray overcast sky, low cloud layer, flat texture, realistic lighting

Estratos: Las grises  

Cómo se ve:  
Capa uniforme gris. Cubre todo el cielo.  

Qué significa:  
Cielo cerrado con posible llovizna.  

Acción:  
Llevá abrigo o impermeable.  

---

## 5. Nimbostratos

Prompt:
nimbostratus clouds, thick dark rain clouds, continuous rain, overcast sky, realistic

Nimbostratos: Las persistentes  

Cómo se ve:  
Cielo oscuro continuo. Sin formas definidas.  

Qué significa:  
Lluvia constante durante varias horas.  

Acción:  
Planificá actividades bajo techo.  

---

## 6. Altocúmulos

Prompt:
altocumulus clouds, patchy mid level clouds, small cloud clusters, realistic sky

Altocúmulos: Las inestables  

Cómo se ve:  
Nubes en parches pequeños. Distribuidas en grupos.  

Qué significa:  
Inestabilidad en altura. Puede evolucionar.  

Acción:  
Prestá atención a cambios rápidos.  

---

## 7. Altostratos

Prompt:
altostratus clouds, gray-blue cloud layer, sun diffused behind clouds, realistic

Altostratos: Las previas  

Cómo se ve:  
Capa gris azulada. El sol se ve difuso.  

Qué significa:  
Sistema de lluvia en aproximación.  

Acción:  
Prepará abrigo o paraguas.  

---

## 8. Cumulonimbos con yunque

Prompt:
cumulonimbus anvil cloud, flat top storm cloud, dramatic sky, realistic

Yunque: Las severas  

Cómo se ve:  
Parte superior plana extendida. Base oscura.  

Qué significa:  
Tormenta madura e intensa.  

Acción:  
Evitá exposición al aire libre.  

---

## 9. Tormenta eléctrica

Prompt:
lightning storm, dark clouds, lightning strike, heavy rain, realistic, high detail

Tormenta eléctrica: Las intensas  

Cómo se ve:  
Cielo oscuro con relámpagos. Lluvia fuerte visible.  

Qué significa:  
Actividad eléctrica con precipitaciones intensas.  

Acción:  
Buscá resguardo inmediato.  

---

## 10. Lluvia intensa

Prompt:
heavy rain, dark clouds, rain streaks, wet environment, realistic

Lluvia intensa: Las constantes  

Cómo se ve:  
Caída abundante de agua. Baja visibilidad.  

Qué significa:  
Precipitación fuerte sostenida.  

Acción:  
Evitá circular si no es necesario.  

---

## 11. Llovizna

Prompt:
light drizzle, gray sky, fine rain, low contrast, realistic

Llovizna: Las leves  

Cómo se ve:  
Gotas finas casi imperceptibles.  

Qué significa:  
Precipitación débil pero continua.  

Acción:  
Llevá algo liviano para cubrirte.  

---

## 12. Niebla

Prompt:
fog, low visibility, dense mist, soft light, realistic environment

Niebla: Las cerradas  

Cómo se ve:  
Ambiente blanquecino. Visibilidad muy reducida.  

Qué significa:  
Condensación a nivel del suelo. Riesgo al circular.  

Acción:  
Reducí velocidad o evitá salir.  

---

## 13. Neblina

Prompt:
mist, light fog, soft haze, low contrast, realistic

Neblina: Las suaves  

Cómo se ve:  
Ligera bruma. Se ve pero difuso.  

Qué significa:  
Humedad en el aire sin gran impacto.  

Acción:  
Mantené precaución al conducir.  

---

## 14. Frente frío

Prompt:
cold front clouds, dramatic sky change, dark clouds approaching, realistic

Frente frío: Los bruscos  

Cómo se ve:  
Cambio rápido de nubes. Oscurecimiento.  

Qué significa:  
Descenso de temperatura y tormentas.  

Acción:  
Abrigate y preparate para lluvia.  

---

## 15. Frente cálido

Prompt:
warm front clouds, layered clouds, gradual sky change, realistic

Frente cálido: Los progresivos  

Cómo se ve:  
Capas de nubes que aumentan gradualmente.  

Qué significa:  
Cambio lento con lluvias posteriores.  

Acción:  
Prevé clima inestable más adelante.  

---

## 16. Granizo

Prompt:
hail storm, ice pellets falling, storm clouds, intense weather, realistic

Granizo: Los destructivos  

Cómo se ve:  
Caída de hielo desde el cielo.  

Qué significa:  
Tormenta severa con daño potencial.  

Acción:  
Protegé objetos y buscá refugio.  

---

## 17. Ráfagas de viento

Prompt:
strong wind, trees bending, dust in air, dramatic sky, realistic

Viento fuerte: Los impredecibles  

Cómo se ve:  
Movimiento brusco de árboles y objetos.  

Qué significa:  
Corrientes intensas de aire.  

Acción:  
Asegurá objetos sueltos.  

---

## 18. Ola de calor

Prompt:
heatwave, bright sun, dry sky, high temperature environment, realistic

Ola de calor: Las extremas  

Cómo se ve:  
Cielo despejado con sol intenso.  

Qué significa:  
Temperaturas muy elevadas sostenidas.  

Acción:  
Hidratate y evitá exposición prolongada.  

---

## 19. Heladas

Prompt:
frost, frozen ground, cold morning, ice crystals, realistic

Heladas: Las frías  

Cómo se ve:  
Superficies cubiertas de hielo.  

Qué significa:  
Temperaturas bajo cero.  

Acción:  
Abrigate y protegé cultivos.  

---

## 20. Tormenta de polvo

Prompt:
dust storm, brown sky, low visibility, strong winds, realistic

Tormenta de polvo: Las secas  

Cómo se ve:  
Aire cargado de tierra. Visibilidad baja.  

Qué significa:  
Vientos fuertes levantando polvo.  

Acción:  
Evitá exposición y protegé vías respiratorias.  

---

## 21. Cielo despejado

Prompt:
clear sky, bright blue sky, no clouds, natural lighting, realistic

Cielo despejado: Los ideales  

Cómo se ve:  
Cielo azul sin nubes.  

Qué significa:  
Condiciones estables.  

Acción:  
Aprovechá actividades al aire libre.  

---

## 22. Nubosidad parcial

Prompt:
partly cloudy sky, sun and clouds, soft light, realistic

Parcialmente nublado: Los variables  

Cómo se ve:  
Mezcla de sol y nubes.  

Qué significa:  
Condiciones cambiantes leves.  

Acción:  
No requiere ajustes importantes.  

---

# SkyPulse — Módulo Aeronáutico (METAR / SPECI / TAF)

Extensión del sistema orientada a **interpretación operativa para seguridad**.

El objetivo no es enseñar teoría aeronáutica completa.  
Es traducir reportes en **riesgo + decisión clara**.

---

## Propósito

Integrar datos aeronáuticos en el mismo formato del sistema:

- interpretar condiciones reales (METAR / SPECI)
- anticipar evolución (TAF)
- traducir a impacto operativo
- generar acción concreta

---

## Tipos de reportes

### METAR

Reporte meteorológico rutinario de aeródromo.

- frecuencia: cada 30–60 min
- representa condiciones actuales

Uso principal:

- evaluar condiciones reales antes de operar

---

### SPECI

Reporte especial cuando hay cambios significativos.

Se emite cuando:

- empeora visibilidad
- cambia viento bruscamente
- aparecen fenómenos peligrosos

Uso principal:

- detectar deterioro rápido

---

### TAF

Pronóstico de aeródromo.

- rango: 9 a 30 horas
- incluye evolución temporal

Uso principal:

- planificación de vuelo

---

## Variables críticas (lo que importa de verdad)

El agente debe enfocarse en:

### Viento

- dirección y velocidad
- ráfagas (G)

Impacto:

- despegue / aterrizaje
- crosswind

---

### Visibilidad

- medida en metros

Impacto:

- operaciones VFR / IFR
- seguridad en rodaje

---

### Techo de nubes

- capas: FEW / SCT / BKN / OVC
- altura en pies

Impacto:

- mínimos operativos
- tipo de vuelo permitido

---

### Fenómenos

Ejemplos:

- TS (tormenta)
- RA (lluvia)
- FG (niebla)
- GR (granizo)

Impacto:

- riesgo directo

---

### Presión (QNH)

- afecta altimetría

---

## Interpretación simplificada (clave del sistema)

El agente NO debe devolver el METAR crudo.

Debe hacer:

1. parseo
2. interpretación
3. traducción a riesgo
4. acción

---

## Formato de salida (adaptado a SkyPulse)

Cómo se ve:
[condición observable]

Qué significa:
[impacto operativo]

Acción:
[decisión concreta]

---

## Ejemplo 1 — METAR

Entrada:

SACO 121200Z 18015G25KT 2000 TSRA BKN020 OVC040 18/16 Q1013

Salida:

Tormenta en aeródromo: Riesgo alto  

Cómo se ve:  
Tormenta con lluvia. Viento con ráfagas fuertes.  

Qué significa:  
Condiciones peligrosas para despegue y aterrizaje.  

Acción:  
Evitar operación o demorar salida.  

---

## Ejemplo 2 — Baja visibilidad

Entrada:

SAEZ 121000Z 00000KT 0500 FG OVC002 12/11 Q1020

Salida:

Niebla densa: Condición crítica  

Cómo se ve:  
Visibilidad muy baja. Cielo completamente cubierto.  

Qué significa:  
Operaciones limitadas o imposibles en VFR.  

Acción:  
No operar sin condiciones IFR habilitadas.  

---

## Ejemplo 3 — TAF

Entrada:

TAF SACO 121100Z 1212/1312 18010KT 9999 SCT030
TEMPO 1215/1220 3000 TSRA

Salida:

Tormentas previstas: Riesgo intermitente  

Cómo se ve:  
Condiciones estables con tormentas temporales.  

Qué significa:  
Ventanas de inestabilidad durante el período.  

Acción:  
Planificar evitando horas críticas.  

---

## Reglas del agente

### Qué hacer

- simplificar sin perder seguridad
- priorizar riesgo sobre detalle
- detectar condiciones críticas

### Qué evitar

- devolver códigos sin interpretar
- explicaciones largas
- lenguaje excesivamente técnico
- ignorar fenómenos peligrosos

---

## Niveles de riesgo (interno)

El agente debe clasificar implícitamente:

- bajo
- moderado
- alto
- crítico

Esto impacta:

- etiqueta
- acción

---

## Fenómenos críticos (prioridad alta)

Si aparecen, escalar riesgo automáticamente:

- TS (tormenta)
- +TSRA (tormenta fuerte)
- FG (niebla)
- GR (granizo)
- GxxKT (ráfagas fuertes)
- visibilidad < 3000 m
- techo < 1000 ft

---

## Principio de seguridad

Si hay duda:

→ el agente debe ser conservador

---

## Integración con SkyPulse

Este módulo alimenta el mismo sistema visual:

- genera tarjetas
- mantiene formato corto
- agrega valor operativo

---

## Resultado esperado

El usuario no necesita entender METAR.

Solo necesita saber:

- si puede operar
- qué tan riesgoso es
- qué hacer

---

Este módulo convierte datos aeronáuticos en decisiones simples alineadas con seguridad operacional.

---

## Rol del agente

El agente no genera contenido libre.

Flujo:

1. recibe fenómeno
2. consulta fuente o base interna
3. genera salida estructurada
4. adapta lenguaje

---

## Restricciones de diseño

- lenguaje simple
- máximo 4 bloques
- cada bloque breve (2–3 líneas)
- siempre incluir decisión
- evitar ambigüedad

---

## Estado del sistema (marzo 2026)

### Funciona

- API operativa en Render
- endpoint de salud: `/api/v1/health`
- Windy como fuente principal
- seguridad HTTP (CSP, Permissions-Policy)
- rutas protegidas con API key
- `/api/v1/metrics` protegido
- rutas debug controladas por flag
- carga paralela en frontend (Promise.all)

---

### Problemas detectados

- cold start en Render (latencia alta)
- complejidad por múltiples fuentes
- API key expuesta en frontend
- build lento por dependencias mezcladas
- logs ruidosos
- integración WRF-SMN inestable (dependencia `h5py`)

---

## Despliegue


| Capa     | Plataforma | Notas                      |
| -------- | ---------- | -------------------------- |
| Frontend | Vercel     | conectado al repo          |
| Backend  | Render     | `uvicorn` desde `apps/api` |


---

## Variables de entorno críticas

Solo nombres (no incluir valores):


| Variable                       | Uso                   |
| ------------------------------ | --------------------- |
| `VALID_API_KEYS`               | autenticación API     |
| `WINDY_POINT_FORECAST_API_KEY` | acceso a Windy        |
| `WRF_SMN_ENABLED`              | activar WRF           |
| `ENABLE_DEBUG_ROUTES`          | rutas de debug        |
| `RISK_AGENTS_ENABLED`          | agentes en background |
| credenciales AWS               | acceso S3 si aplica   |


Ver detalle completo en `apps/api/README.md`

---

## Reglas para nuevas iteraciones

### 1. Un solo proveedor en v1

Evitar múltiples fuentes hasta estabilizar producto.

### 2. Sin fusión de modelos

No mezclar Windy + WRF en etapas tempranas.

### 3. Backend mínimo

Usar backend solo para:

- proxy de claves
- rate limiting
- seguridad

### 4. Separación de dependencias

Mantener:

- `requirements-prod.txt`
- sin herramientas de desarrollo en producción

### 5. Secretos fuera del frontend

Nunca exponer claves sensibles en el bundle.

---

## Módulo: Desastres Naturales Mundiales

7 eventos de impacto global con datos históricos verificados, curiosidades y fuentes oficiales de seguimiento en tiempo real.

**Formato extendido (6 bloques):** incluye Dato histórico, Curiosidad y URLs oficiales además de los 3 bloques base.

**Fenómenos cubiertos:** Terremotos · Inundaciones · Tornados · Huracanes · Incendios · Tsunamis · Micro tsunamis

**Catálogo completo:** [`CATALOG_desastres.md`](./CATALOG_desastres.md)

**Fuentes oficiales utilizadas:** USGS · NOAA · Copernicus EMS · NASA FIRMS · GWIS · Pacific Tsunami Warning Center

---

## Dirección del proyecto

SkyPulse evoluciona hacia:

- motor de interpretación meteorológica y de desastres naturales
- sistema narrativo basado en fenómenos
- interfaz orientada a decisiones rápidas

---

## Estrategia de generación de contenido

Opciones:

### A. Plantillas (recomendado v1)

- contenido predefinido por fenómeno
- bajo costo y alta consistencia

### B. LLM

- flexible
- mayor costo y menor control

### C. Híbrido (objetivo)

- base estructurada + variaciones dinámicas

---

## Documentación adicional

- `docs/auditorias/`
- `apps/api/README.md`

