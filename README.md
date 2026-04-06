# SkyPulse — Catálogo del Cielo

## Qué es SkyPulse

SkyPulse no es un panel meteorológico tradicional.

Es un sistema diseñado para transformar datos complejos en decisiones concretas. Combina:

- Visualización de fenómenos atmosféricos
- Interpretación simplificada
- Generación de contenido narrativo estructurado

La cuestión es esta: no responde solo qué está pasando, sino qué implica y qué debería hacer el usuario.

---

## Objetivo del sistema

Convertir datos meteorológicos en información accionable.

Esto implica:

- Reducir complejidad técnica
- Traducir modelos y reportes a lenguaje claro
- Generar contenido consistente y reutilizable
- Enfocar siempre en impacto + decisión

---

## Estructura conceptual

SkyPulse se apoya en dos capas principales:

### 1. Catálogo visual del cielo (UI actual)

Representado en el HTML proporcionado.

Organiza fenómenos en categorías:

- Nubes altas
- Nubes medias
- Nubes bajas
- Desarrollo vertical
- Fenómenos especiales
- Módulo aeronáutico

Cada elemento visual es una “unidad narrativa”.

---

### 2. Generación de historias meteorológicas

Cada fenómeno sigue una estructura fija:
[Nombre del fenómeno]
Cómo se ve: Descripción visual simple.
Qué significa: Interpretación meteorológica.
Contexto: Cuándo aparece o qué indica.
Decisión: Acción concreta para el usuario.

Esto es el núcleo del sistema.

El HTML ya implementa parcialmente esta lógica en formato visual.

---

## Relación con el HTML

El archivo HTML actúa como:

### Interfaz de consumo

- Presenta fenómenos como tarjetas (`cloud-card`)
- Usa imágenes + texto narrativo
- Inclye niveles de alerta visual (`alert-*`)
- Permite exploración progresiva (HTMX toggle)

### Componentes clave

#### Tarjeta de fenómeno

Cada tarjeta contiene:

- Nombre común + técnico
- Altitud y composición
- Estado visual (alerta)
- Narrativa simplificada
- Extensión aeronáutica (expandible)

#### Sistema de alertas

Clases disponibles:

- `alert-clear`
- `alert-watch`
- `alert-warn`
- `alert-crit`
- `alert-neutral`
- `alert-info`

Representan nivel de impacto, no solo estética.

#### Filtros

Barra sticky superior:

- Filtrado por tipo de nube
- Segmentación conceptual del cielo
- Entrada al modo aeronáutico

---

## Módulo aeronáutico

Integrado como extensión dentro de cada fenómeno.

No enseña teoría.
Traduce condiciones a riesgo operativo.

### Entrada esperada

- METAR
- SPECI
- TAF

### Variables críticas

- Viento (dirección, intensidad, ráfagas)
- Visibilidad
- Techo de nubes
- Fenómenos (TS, RA, FG, GR, etc.)
- Presión (QNH)

---

## Lógica de interpretación

El sistema no expone datos crudos.

Pipeline esperado:
dato → parseo → interpretación → impacto → decisión

---

## Formato de salida aeronáutico
Cómo se ve: Condición observable actual
Qué significa: Impacto operativo
Acción: Decisión concreta

Esto es consistente con la narrativa del catálogo visual.
