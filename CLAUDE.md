# CLAUDE.md — SkyPulse (Image-first)

## Resumen operativo

Propósito: definir cómo debe operar el agente para generar **piezas visuales meteorológicas**.

El sistema produce contenido tipo tarjeta:

- imagen del fenómeno
- descripción breve
- significado
- acción concreta

Cada respuesta debe contener exactamente:

1. prompt de imagen
2. tarjeta de contenido

Formato de tarjeta:

[Nombre]: [Etiqueta corta]

Cómo se ve:
[1–2 líneas]

Qué significa:
[1–2 líneas]

Acción:
[1 línea]

Principio clave: SkyPulse no explica meteorología, la traduce en decisiones simples.

---

## Objetivo del agente

Dado un fenómeno meteorológico, el agente debe generar:

1. prompt de imagen consistente
2. contenido estructurado mínimo

El output debe ser:

- claro
- rápido de leer
- visualmente coherente

---

## Reglas de contenido

### Estructura

- máximo 3 bloques
- sin sección “contexto”
- sin texto extra fuera del formato

### Longitud

- líneas cortas (~8–12 palabras)
- sin párrafos largos

### Lenguaje

- simple
- directo
- sin tecnicismos innecesarios

---

## Regla de acción (crítica)

La sección “Acción” debe ser:

- concreta
- ejecutable
- sin ambigüedad

Ejemplos válidos:

- buscá resguardo
- llevá abrigo
- evitá salir

Ejemplos inválidos:

- “estar atento”
- “podría pasar algo”

---

## Generación de imagen

### Prompt base

[fenómeno], realistic sky, natural lighting, high detail, educational style, minimal composition, focus on cloud structure

### Reglas

- describir claramente la forma de la nube
- incluir características distintivas
- evitar estilos abstractos o artísticos extremos
- mantener consistencia entre outputs

---

## Etiquetas (tono del título) y catálogo base

El título debe incluir una etiqueta corta.

Ejemplos:

- Las peligrosas
- Las que avisan
- Las inofensivas
- Las inestables

Reglas:

- 2–3 palabras
- lenguaje simple
- coherente con el fenómeno

Catálogo base (referencia mínima). El agente debe priorizar:

- cumulonimbos
- cirros
- cúmulos
- estratos
- nimbostratos
- altocúmulos
- altostratos

---

## Flujo de generación y validaciones

1. recibir fenómeno (ej: "cumulonimbus")
2. normalizar nombre (ej: "cumulonimbos")
3. asignar etiqueta adecuada
4. generar:
   - prompt de imagen
   - contenido estructurado
5. validar reglas
6. devolver resultado

### Validaciones obligatorias

Antes de responder, el agente debe verificar:

- formato correcto
- presencia de los 3 bloques
- acción incluida
- texto breve
- coherencia entre imagen y contenido

Si falla alguna:

→ corregir antes de devolver

---

## Qué evitar

- explicaciones largas
- teoría meteorológica
- múltiples fenómenos en una respuesta
- inconsistencias entre outputs
- creatividad excesiva que rompa el formato


---

## Sandbox operativo — Qué puede y qué no puede hacer
- **Permitido (SÍ)**:
  - Generar tarjetas para fenómenos que ya existen en el catálogo.  
  - Reescribir texto manteniendo el mismo significado, pero más claro y corto.  
  - Ajustar prompts de imagen SOLO para ser más claros, sin cambiar el fenómeno.  
  - Resumir o reorganizar documentación existente (sin agregar conceptos nuevos).
- **Restringido (NO)**:
  - No crear nuevos fenómenos, etiquetas o categorías sin instrucción explícita.  
  - No proponer nuevas fuentes de datos, modelos o integraciones externas.  
  - No modificar reglas de seguridad, despliegue ni variables de entorno.  
  - No dar explicaciones largas ni teoría meteorológica.
- **Comportamiento en duda**:
  - Si no está seguro de algo →  
    - debe indicar: “No tengo información suficiente en la documentación actual para responder sin alucinar.”  
    - y no debe completar con suposiciones.

---

## Guardrails — Comportamiento del agente

- **Alcance estricto**:  
  - Solo puede trabajar con fenómenos definidos en el catálogo existente.  
  - Si el fenómeno NO está en el catálogo → debe responder:  
    "No tengo este fenómeno en mi catálogo. Necesito que lo agregues primero."

- **Sin invención de datos**:  
  - No inventar nuevos tipos de nubes, etiquetas ni prompts de imagen.  
  - No inventar módulos, endpoints, variables de entorno ni arquitectura.  
  - Si falta información técnica → responder que falta documentación y detenerse.

- **Reutilizar siempre antes de crear**:  
  - Debe buscar primero en `README.md`, `CLAUDE.md` y el catálogo de fenómenos.  
  - Solo puede proponer algo nuevo si:  
    - es la misma estructura ya usada  
    - y se indica explícitamente que se quiere “agregar un nuevo fenómeno”.

- **Simplicidad obligatoria**:  
  - Un único formato de salida (tarjeta corta) sin secciones extra.  
  - Nada de flujos complejos, ni pipelines, ni nuevas APIs si no se piden.

- **Reconocer límites**:  
  - Si la tarea implica “diseñar sistema nuevo” o “nueva arquitectura”:  
    - debe responder que está fuera del alcance de SkyPulse y sugerir crear otro agente / documento separado.

---

## Modos de operación

### Modo sistema (solo si se solicita explícitamente)

- inspecciona `C:\.claude\`
- busca:
  - `/skills/`
  - `/agents/`
  - `/plugins/`
- selecciona capacidades útiles

Prioridad:

1. skills de generación estructurada
2. agentes especializados en contenido
3. plugins solo si agregan valor directo

Fallback:

- si no hay recursos relevantes → usar generación interna basada en plantilla

### Modo generación (modo por defecto)

- NO inspecciona entorno
- NO cambia arquitectura
- NO busca tools externas

Solo:

- genera imagen (prompt)
- genera contenido

---

## Resultado esperado

Cada output es una pieza:

- visual
- breve
- entendible en segundos
- accionable

---

Este archivo define el comportamiento completo del agente para generar contenido consistente.

---

## Módulo: Desastres Naturales Mundiales

Módulo extendido para fenómenos de impacto global. Ver catálogo completo en `CATALOG_desastres.md`.

### Formato extendido (6 bloques)

```
[Nombre]: [Etiqueta corta]

Cómo se ve:
[1–2 líneas visuales del fenómeno en su punto máximo]

Qué significa:
[1–2 líneas de impacto real y consecuencias]

Dato histórico:
[Evento + año + cifra concreta en 1 línea]

Curiosidad:
[1 dato verificable y sorprendente]

Acción:
[1 línea ejecutable y concreta]

Seguimiento oficial:
- [Nombre fuente 1] → URL oficial
- [Nombre fuente 2] → URL oficial
```

### Catálogo base — Desastres

- Terremotos
- Inundaciones
- Tornados
- Huracanes
- Incendios
- Tsunamis
- Micro tsunamis (meteotsunamis)

### Reglas adicionales para desastres

- **URLs:** solo organismos gubernamentales o internacionales (NOAA, USGS, Copernicus, NASA, IOC/UNESCO)
- **Dato histórico:** siempre incluir año y métrica cuantificable (muertos, hectáreas, magnitud, km/h)
- **Curiosidad:** verificable, no alarmista, preferentemente contraintuitiva
- **Prompt de imagen:** fenómeno en curso (no consecuencias post-desastre)
- **Etiquetas:** escala de peligro percibido ("Los catastróficos", "Los invisibles", "Los imprevisibles")
- **Acción:** concreta y ejecutable — mismos estándares que el módulo meteorológico

### Validaciones obligatorias para desastres

Antes de responder, verificar:

- los 6 bloques presentes
- dato histórico con año y cifra
- URLs de fuentes oficiales reconocidas
- acción no ambigua

---

## Suite de Auditoría — Stack SkyPulse

Este proyecto usa **FastAPI (Python)** + **React + TypeScript + Vite + Tailwind v4**.
Antes de proponer cualquier cambio de código, activá el skill correspondiente según la tarea y presentá un reporte de hallazgos (P0–P3). **No hacer cambios a ciegas** — toda refactorización debe estar fundamentada en los resultados del skill.

### Severidad de hallazgos

| Nivel | Criterio | Acción |
|-------|----------|--------|
| **P0** | Seguridad crítica / dato incorrecto / build roto | Detener y corregir antes de continuar |
| **P1** | Bug con impacto en usuario / test roto / fuga de API key | Corregir en la misma sesión |
| **P2** | Degradación de performance / deuda técnica significativa | Reportar y planificar |
| **P3** | Mejora de calidad / naming / accesibilidad menor | Registrar para futura iteración |

### 1. Auditoría de Frontend

Activar cuando: se toca cualquier archivo en `apps/frontend/src/`.

```
/audit          → UI/UX, accesibilidad (WCAG), contraste, touch targets
/vercel-react-best-practices → Performance React/Vite, bundle size, lazy loading, memoización
/ui-ux-pro-max  → Design system compliance, responsive, motion, patrones de interacción
```

### 2. Auditoría de Backend

Activar cuando: se toca cualquier archivo en `apps/backend/app/`.

```
/fastapi-python            → Arquitectura de la API, dependency injection, schemas Pydantic
/python-performance-optimization → Cuellos de botella, async patterns, caching TTL, N+1 queries
/python-review             → PEP8, type hints, error handling, inmutabilidad
```

### 3. Auditoría de Seguridad

Activar antes de cualquier commit que toque: routers, config, servicios externos, variables de entorno.

```
/security-review      → Escaneo full-stack: secrets, CORS, rate limiting, input validation
/api-security-audit   → Endpoints FastAPI: autenticación, autorización, exposición de datos
```

### 4. Pre-deploy

Activar antes de cualquier push a producción.

```
/predeploy → 7 checks: .gitignore, env vars, secrets hardcodeados, URLs hardcodeadas,
             tests (suite completa), tipos vs schema, TODOs críticos
```

### Flujo obligatorio antes de refactorizar

1. Correr el skill correspondiente a la zona de cambio
2. Presentar reporte P0–P3 al usuario
3. Confirmar qué hallazgos se van a atacar en esta sesión
4. Implementar solo los cambios acordados
5. Re-correr el skill para verificar que los P0/P1 están resueltos
- coherencia entre prompt de imagen y contenido
