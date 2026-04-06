# 🌤️ SkyPulse — Catálogo del Cielo

Un catálogo visual interactivo de nubes y fenómenos meteorológicos, diseñado para cualquier persona curiosa sobre lo que pasa en el cielo — sin necesidad de conocimiento técnico previo.

[![Deploy con Vercel](https://img.shields.io/badge/Deploy-Vercel-black?logo=vercel)](https://skypulseinfo.vercel.app)
[![Licencia](https://img.shields.io/badge/Licencia-MIT-blue)](LICENSE)

---

## ¿Qué es SkyPulse?

SkyPulse convierte la meteorología en algo accesible. Cada entrada del catálogo incluye una fotografía real de la nube o fenómeno, su nombre técnico y su nombre común, la altitud a la que se forma, qué significa para el clima, un nivel de alerta claro (verde / amarillo / naranja / rojo) y un dato curioso.

Además, cada nube tiene un panel expandible con su **significado aeronáutico**: qué implica para un piloto, qué peligros representa y cómo se reporta en la jerga oficial (METAR, SIGMET, PIREP).

---

## Contenido del catálogo

El catálogo está organizado en seis categorías filtrables:

**Nubes altas** (sobre los 6.000 m, compuestas de cristales de hielo): Cirros, Cirrostratos y Cirrocúmulos.

**Nubes medias** (entre 2.000 y 6.000 m, mezcla de agua y hielo): Altocúmulos y Altostratos.

**Nubes bajas** (por debajo de los 2.000 m, principalmente agua líquida): Estrato, Estratocúmulos y Nimboestrato.

**Nubes verticales** (se desarrollan desde la superficie hasta la tropopausa): Cúmulo y Cumulonimbo.

**Nubes especiales** (formaciones poco comunes): Nube Lenticular, Mammatus y Niebla.

**Fenómenos aeronáuticos** (invisibles a simple vista pero críticos para la seguridad en vuelo): Corriente en Chorro (Jet Stream), Cizalladura del Viento (Wind Shear), Engelamiento en Vuelo (Aircraft Icing), Turbulencia en Aire Claro (CAT) y Estela Turbulenta (Wake Turbulence).

---

## Tecnología utilizada

SkyPulse es un sitio 100% estático — sin servidor, sin base de datos, sin dependencias de backend. Funciona con un único archivo HTML que carga tres recursos externos vía CDN:

- **Tailwind CSS** para los estilos utilitarios.
- **HTMX** para el patrón de expansión/colapso de los paneles aeronáuticos sin recargar la página.
- **Google Fonts** para la tipografía (Playfair Display + DM Sans).

Las imágenes provienen de **Wikimedia Commons** bajo licencias Creative Commons, con un sistema de fallback automático en caso de error de carga.

---

## Estructura del repositorio

```
skypulse/
├── src/
│   └── index.html     # El catálogo completo — todo el sitio en un archivo
├── vercel.json        # Configuración de Vercel: apunta la raíz del sitio a src/
└── README.md          # Este archivo
```

---

## Cómo hacer cambios

Dado que el sitio es un archivo HTML estático, cualquier modificación se hace directamente sobre `src/index.html` desde la interfaz de GitHub (funciona perfectamente desde el celular):

Para agregar una nube nueva: copiás cualquier bloque `<article class="cloud-card">` existente, cambiás los datos y pegás el nuevo bloque en la sección correspondiente.

Para actualizar una imagen: buscás la URL en Wikimedia Commons (commons.wikimedia.org), copiás el enlace de la versión que quieras y lo reemplazás en el atributo `src` del `<img>` correspondiente.

Cada vez que guardás un commit en GitHub, Vercel redesplega el sitio automáticamente en menos de 30 segundos.

---

## Fuentes y licencias

Las imágenes provienen de **Wikimedia Commons** bajo diversas licencias Creative Commons. La clasificación de nubes está basada en el [Atlas Internacional de Nubes](https://cloudatlas.wmo.int) de la Organización Meteorológica Mundial (OMM).

La información aeronáutica tiene fines estrictamente divulgativos. Para operaciones reales, siempre consultar la documentación oficial de OACI y la autoridad de aviación civil correspondiente.

---

## Licencia

MIT — libre para usar, modificar y distribuir.

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
