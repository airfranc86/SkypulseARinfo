# 🌤️ SkyPulse — Catálogo del Cielo

Un catálogo visual interactivo de nubes, fenómenos meteorológicos y meteorología aeronáutica — diseñado para cualquier persona curiosa sobre lo que pasa en el cielo, sin conocimiento técnico previo.

[![Deploy](https://img.shields.io/badge/Deploy-Vercel-black?logo=vercel)](https://skypulseinfo.vercel.app)
[![Licencia](https://img.shields.io/badge/Licencia-MIT-blue)](LICENSE)

---

## ¿Qué es SkyPulse?

SkyPulse convierte la meteorología en algo accesible. El proyecto tiene tres secciones principales:

**Catálogo de nubes** — cada entrada incluye fotografía real, nombre técnico y común, altitud de formación, barra de peligro visual, significado para el clima, cuándo y cómo observarla, y un dato curioso etimológico. Cada nube tiene además un panel expandible con su significado aeronáutico.

**METAR & TAF** — sección educativa que enseña a leer reportes meteorológicos aeronáuticos reales. Incluye consulta en vivo de cualquier aeródromo del mundo por código ICAO, desglose campo por campo con indicador de categoría de vuelo (VFR / MVFR / IFR / LIFR), buscador de códigos ICAO por región, ejemplos anotados y glosario completo.

**Lluvias** — guía práctica que explica qué tipo de lluvia produce cada nube, su intensidad, duración y contexto estacional.

---

## Contenido del catálogo

El catálogo está organizado en seis categorías filtrables:

**Nubes altas** (sobre los 6.000 m · cristales de hielo): Cirros, Cirrostratos y Cirrocúmulos.

**Nubes medias** (entre 2.000 y 6.000 m · agua y hielo): Altocúmulos y Altostratos.

**Nubes bajas** (por debajo de los 2.000 m · agua líquida): Estrato, Estratocúmulos y Nimboestrato.

**Nubes verticales** (desde la superficie hasta la tropopausa): Cúmulo y Cumulonimbo.

**Nubes especiales** (formaciones poco comunes): Nube Lenticular, Mammatus y Niebla.

**Fenómenos aeronáuticos** (invisibles pero críticos): Corriente en Chorro, Cizalladura del Viento, Engelamiento en Vuelo, Turbulencia en Aire Claro (CAT) y Estela Turbulenta.

---

## Tecnología

SkyPulse es un sitio 100% estático — sin servidor ni base de datos. Tres páginas HTML independientes con el mismo sistema de diseño.

**Frontend**
- Tailwind CSS (CDN) para estilos utilitarios
- Google Fonts — Playfair Display + DM Sans + JetBrains Mono
- JavaScript vanilla para filtros, acordeones, modal y llamadas a la API

**API de datos meteorológicos**
- CheckWX API para consulta de METAR y TAF en tiempo real
- Plan gratuito: 10.000 requests/mes
- La clave de API se configura directamente en el archivo según el entorno de uso

**Imágenes**
- ZME Science CDN para fotografías de nubes (sin restricciones de hotlinking)
- UCAR / NSF Center for Science Education para Lenticular y Mammatus (dominio público)
- Unsplash CDN para categorías adicionales

**Deploy**
- Vercel como plataforma de hosting estático
- GitHub como repositorio y origen del deploy automático

---

## Estructura del repositorio

```
skypulse/
├── src/
│   ├── index.html     # Catálogo principal de nubes
│   ├── metar.html     # Sección METAR & TAF con consulta en vivo
│   └── lluvia.html    # Guía de tipos de lluvia por nube
├── vercel.json        # Apunta outputDirectory a src/
└── README.md
```

---

## Configuración de la API

La sección METAR requiere una clave de CheckWX. Para obtenerla:

1. Registrarse en [checkwx.com](https://www.checkwx.com) — el plan gratuito es suficiente para uso educativo.
2. En `src/metar.html`, localizar la constante `CHECKWX_KEY` dentro del bloque `<script>` y asignarle la clave obtenida.

Para producción con tráfico significativo se recomienda mover la llamada a la API a una función serverless que actúe como proxy y mantenga la clave fuera del código cliente.

---

## Deploy

El sitio se despliega automáticamente en Vercel con cada push a la rama principal. La configuración en `vercel.json` indica que el directorio raíz del sitio es `src/`:

```json
{
  "outputDirectory": "src"
}
```

Para desplegarlo en una cuenta propia: importar el repositorio desde vercel.com — Vercel lee el `vercel.json` automáticamente.

---

## Cómo hacer cambios

El sitio se puede editar directamente desde la interfaz web de GitHub, incluyendo desde el celular.

Para agregar una nube: copiar cualquier bloque `<article class="cloud-card">` en `index.html`, actualizar los datos y pegarlo en la sección correspondiente.

Para actualizar una imagen: reemplazar la URL en el atributo `src` del `<img>` correspondiente. Se recomienda usar fuentes sin restricciones de hotlinking como Unsplash CDN o ZME Science CDN.

Para agregar un aeródromo al modal ICAO: agregar un objeto al array `ICAO_DB` en `metar.html` con la estructura `{code, city, country, region, full}`.

Cada commit redespliega el sitio en Vercel en menos de 30 segundos.

---

## Fuentes y créditos

La clasificación de nubes está basada en el [Atlas Internacional de Nubes](https://cloudatlas.wmo.int) de la Organización Meteorológica Mundial (OMM).

La información aeronáutica tiene fines estrictamente divulgativos. Para operaciones reales, consultar siempre la documentación oficial de OACI y la autoridad de aviación civil correspondiente.

---

## Licencia

MIT — libre para usar, modificar y distribuir.
