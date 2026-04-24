# SkyPulse — Plan de auditoría y road‑map: Lluvias, METAR/TAF y apps de predicción

Este plan está pensado para que puedas:
- Revisar el estado actual de SkyPulse (estructura, UX, técnico).
- Definir claramente qué tipo de experiencia de usuario buscás en:
  - la sección **“Lluvias”**,
  - la sección **“Aeronáutico: METAR & TAF”**,
  - y en el **modelo de predicción de tu celular / apps de radar**.
- Diseñar luego una experiencia coherente, sin sobrecargar el producto ni perder el foco.

---

## 1. Objetivo de esta fase

### 1.1. En la sección **Lluvias**

Que la subpágina de Lluvias:

- Relacione **cada tipo de nube** con:
  - **Intensidad de lluvia** (llovizna, moderada, fuerte, aguacero, tormenta).  
  - **Duración típica** (corta, media, larga, prolongada).
- Hable también de **granizo**, **downburst** y **mammatus**:
  - Qué son, cómo se reconocen visualmente.
  - Qué implica cada uno para seguridad de vuelo o para actividades al aire libre.
- Use **“probabilidades”** o **“chances”** en lugar de tecnicismos:  
  - ¿Cuán probable es que llueva?  
  - ¿Cuán probable es granizo o ráfaga fuerte?  
- Termine con **recomendaciones prácticas** (qué hacer si ves cierto tipo de nube).

### 1.2. En la sección **Aeronáutico**

Mantener el objetivo original de tu plan:

- Auditar la sección “Aeronáutico”.
- Definir el público objetivo (pilotos, estudiantes, entusiastas).
- Diseñar el **modular de enseñanza de METAR/TAF**:
  - Lectura guiada, ejemplos, ejercicios.  
  - Posible integración de datos reales vía API.

### 1.3. En **modelos de predicción y apps externas**

Sumar otros dos bloques:

- **Cómo entender el modelo predictivo de tu celular**  
  - ¿Qué es el “pronóstico de lluvia por hora” en tu app de clima?  
  - ¿Qué significa “chance de lluvia” vs “intensidad” y “precipitación” en mm?

- **Cómo leer una app de radar o satélite**  
  - Interpretar:
    - Colores de radar (lluvia ligera, moderada, fuerte, granizo).
    - Movimiento de la tormenta en el tiempo.
  - En lenguaje simple, sin tutorial de app en sí, sino de **cómo se interpreta la imagen**.

---

## 2. Auditoría general del proyecto

Se mantiene tu bloque original, aplicado ahora también a estos nuevos temas:

### 2.1. Revisión de objetivos y propósito

> **Preguntas previas**:

- ¿Cuál considerás que es hoy el “público principal” de SkyPulse?
  - ¿Pilotos reales, estudiantes, aficionados, VFR only, IF?
- ¿Qué rol tiene hoy la sección “Aeronáutico”?
  - ¿Es un bonus, una sección de nicho o un eje central del proyecto?
- ¿Qué quieres que el usuario *haga* cuando hace clic en:
  - **“Lluvias”**.
  - **“Aeronáutico”**.
  - **Un bloque de “Cómo leer tu app de clima”**?

### 2.2. Auditoría de UX y contenido

> **Preguntas previas**:

- ¿Cómo se siente usar la sección **“Lluvias”** hoy?
  - ¿Es clara, demasiado teórica, o falta relacionarla con decisiones concretas?
- ¿Qué tanto profundo/certero es el contenido de **fenómenos extremos** (granizo, downburst, mammatus)?
- ¿Qué estilo de texto usás:
  - Explicación conceptual.
  - Guía paso a paso.
  - Referencia rápida.

### 2.3. Auditoría técnica

> **Preguntas previas**:

- ¿Qué tecnología está usando realmente la parte **“Lluvias”** y **“Aeronáutico”** hoy?
  - ¿Solo HTML/CSS estático?
  - ¿Hay algo de interactividad con JS/HTMX?
- ¿Cómo se ve el flujo de datos:
  - Todo estático.
  - Datos externos (por ejemplo, METAR/TAF, radar, satélite) entrando posteriormente.
- ¿Qué tan crítico es el límite de recursos (RAM, bundle size) en tu actual stack frente a Vercel?

---

## 3. Refinamiento de la sección “Lluvias”

Vamos a **darle más profundidad visual y práctica** a la subpágina `Lluvias.html`.

### 3.1. Concepto central

La idea de la sección “Lluvias” pasa a ser:

> “**De la nube que ves → a la lluvia que podes esperar → y a las acciones que podes tomar.**”

Se habla de:
- **Intensidad** de lluvia (no solo “llueve” / “no llueve”).
- **Granizo**, **downburst**, **mammatus** como **amplificadores de riesgo**, no como fenómenos aislados.
- **“Chances”** y **“probabilidad”** en lenguaje muy simple.

Sin usar términos como “CAPE”, “CIN”, “shear”, etc., solo consecuencias:  
- “¿Qué puede pasar si sigo volando / si sigo fuera de casa?”  
- “¿Qué sentido tiene que la app de clima muestre ‘lluvia moderada’ versus ‘tormenta fuerte’?”

### 3.2. Contenido conceptual a añadir

Dentro de `Lluvias.html`, podrías tener secciones como:

#### 3.2.1. Intensidad de lluvia según la nube

- Tabla ampliada donde cada tipo de nube explique:
  - Probabilidad de lluvia.
  - Intensidad típica.
  - Duración típica.
  - Riesgo de granizo (sí/no, condición).

> **Ejemplos de lenguaje simple**:

- “Con **Cúmulo** puede que tengas chubascos breves, pero no un día entero de agua.”  
- “Con **Cumulonimbo** las probabilidades de aguacero fuerte, truenos y, a veces, granizo, son altas.”

#### 3.2.2. Granizo y downburst

- **¿Qué es?**  
  - En una frase sencilla:  
    - “Granizo: pedazos de hielo que caen desde nubes muy altas y frías.”  
    - “Downburst: una ráfaga de viento muy fuerte que baja de una nube hacia el suelo, como si la nube ‘cayera de golpe’.”  
- **Cómo se reconoce visualmente**:
  - Nube muy oscura, base muy baja, viento que de repente se vuelve ruidoso y fuerte.  
- **Qué implica**:
  - Peligro para aeronaves bajas (VFR, despegues, aterrizajes).  
  - Dificultad para manejar, caída de objetos, posible daño a estructuras.
- **“Chances” de que ocurra**:
  - No se habla de números duros, sino de “muy baja”, “moderada”, “alta” según el tipo de nube y el contexto.

#### 3.2.3. Mammatus

- **¿Qué son?**  
  - “Bolsas hinchadas que cuelgan de la base de una nube muy activa.”  
- **¿Qué significan?**  
  - Indican turbulencia fuerte en el aire cercano, inestabilidad intensa.  
- **Qué hacer**:
  - Para pilotos: evitar acercarse a la zona.  
  - Para personas en tierra: prepararse para viento fuerte, lluvia fuerte o incluso granizo.

#### 3.2.4. Probabilidades y “chances”

- **Ejemplos de frases simples**:

  - “Si ves **cumulonimbos**, hay **mucha chance** de que llueva fuerte dentro de poco.”  
  - “Si ves solo **estratos**, la lluvia suele ser suave, pero con **alta probabilidad** de que siga durante horas.”  
  - “El granizo **no es seguro** siempre que haya una nube oscura, pero si la nube parece muy ‘cargada’, mejor estar preparado.”

La idea es que el usuario **no sepa la fórmula**, pero sí **tenga una sensación intuitiva**:

- “Si yo veo esto, ¿qué chance de problemas hay?”

### 3.3. Recomendaciones prácticas por nube

- **Para cada tipo de nube** (o grupo de nubes similares):
  - Recomendación de vuelo (si es VFR, mejor no salir, posponer, etc.).  
  - Recomendación de actividades al aire libre (paseos, deportes, eventos).  
  - Recomendación de protección básica (paraguas, buscar refugio, revisar el tiempo antes de salir).

---

## 4. Refinamiento de la sección “Aeronáutico: METAR / TAF”

Se mantiene casi tal como está en tu plan, pero **lo posicionamos como parte integral** del camino de entrenamiento del usuario:

- La sección **“Lluvias”** enseña a **interpretar el cielo**.  
- La sección **“Aeronáutico”** enseña a **interpretar los informes METAR/TAF**, que son el **lado técnico** de lo que ya vieron en “Lluvias”.

### 4.1. Flujo de aprendizaje esperado

- Primero: usuario ve el cielo → entiende qué tipo de nube, qué lluvia, qué riesgo.  
- Luego: cuando hace clic en “Aeronáutico”, aprende:
  - Qué significan todos los códigos del METAR/TAF.
  - Cómo se relacionan con el cielo que ya sabe identificar (Cumulonimbo = Cb, etc.).

### 4.2. Opciones de flujo (repasadas en tu plan)

- **Opción A: “Guía paso a paso”**  
- **Opción B: “Lectura guiada + ejemplos”**

Perfecto las dos, solo hay que elegir cuál es más acotada para tu tiempo.

---

## 5. Nuevo bloque: “Modelo de predicción de tu celular”

Aquí agregamos otra página o sub‑sección accesible desde el footer o desde un bloque de “recursos”:

### 5.1. Idea principal

> “**Entender qué quiere decir tu app de clima, sin leer el manual de la app.**”

No es explicar una app específica, sino **cómo interpretar el modelo de pronóstico** que tu celular usa.

### 5.2. Contenidos clave

- **Qué es “probabilidad de lluvia”**  
  - “No es solo ‘llueve’ o ‘no llueve’, es una **chance**.”  
  - “30 % no es mucha lluvia, 80 % sí.”
- **Intensidad vs. cantidad**  
  - “La app puede decir ‘lluvia’ y ser llovizna o ser aguacero.”  
  - “Importa el **tipo de precipitación** (agua, mezcla, nieve) y **cuánto**.”
- **Horas vs. días**  
  - “La lluvia puede estar concentrada en 20 minutos o repartida en todo el día.”
- **Relación con lo que ves en el cielo**  
  - “Si la app dice ‘lluvia fuerte’ pero el cielo está prácticamente despejado, puede que haya algo de error o retraso.”
  - “Si el cielo está muy oscuro y la app muestra solo ‘lluvia ligera’, es buena idea revisar radar o satélite.”

Esta sección se puede llamar algo así como:

- “¿Cómo entender tu app de clima”  
- O “Leyendo tu modelo de predicción”

### 5.3. Flujo de contenido (propuesta)

- 1. Introducción: ¿Qué es el modelo de prediccción de tu celular?  
- 2. Sección de **“probabilidad vs intensidad”**.  
- 3. Sección de **“cómo relacionar texto con lo que ves en el cielo”**.  
- 4. Recomendaciones prácticas:  
  - ¿Cuándo fiarse de la app?  
  - ¿Cuándo conviene chequear radar o METAR/TAF?

---

## 6. Nuevo bloque: “Cómo leer una app de radar o satélite (en pocas palabras)”

Otra subpágina o bloque dentro de “Lluvias” o “Aeronáutico”:

### 6.1. Idea principal

> “**Entender el lenguaje de colores de radar y satélite, sin ser meteorólogo.**”

No es una guía de la app en sí, sino de cómo se **interpreta la imagen**.

### 6.2. Contenidos clave

- **Radar**:
  - Colores más claros → lluvia ligera.  
  - Colores más oscuros → lluvia moderada o fuerte, posible granizo.  
  - Zonas muy densas y continuas → tormenta consolidada.  
- **Satélite**:
  - Blanco muy brillante → nubes altas, fuertes, muy frías, posible cumulonimbo.  
  - Gris suave → nubes más bajas o débiles.

### 6.3. Ejemplos de lenguaje simple

- “En el radar, el **rojo o morado** te avisa de un parche muy intenso, probablemente con ráfagas y granizo.”  
- “En el satélite, el **blanco brillante** indica nubes que ya están muy desarrolladas y pueden traer lluvia fuerte.”

### 6.4. Flujo sugerido

- 1. Introducción: qué es el radar y el satélite.  
- 2. Sección de “colores y lo que significa cada uno”.  
- 3. Mini‑ejercicio:  
  - Una imagen de ejemplo con marcas; el usuario decide:  
    - “¿Es tormenta fuerte o llovizna?”  
    - “¿Se ve que se va a mover hacia donde estoy?”  
- 4. Recomendaciones prácticas:  
  - “Si veo esto, cierro el paraguas, no salgo a volar, recojo lo que está en el patio, etc.”

---

## 7. Evaluación de riesgos y trade‑offs técnicos (ampliado)

> **Preguntas previas** (se mantiene tu bloque original, pero ahora aplicado también a “Lluvias” y “apps de radar/satélite”):

- ¿Querés integrar **datos reales** de:
  - METAR/TAF.
  - Radar/satélite.
  - Modelos de predicción de celular.
- ¿O prefieres que todo el contenido de **“Lluvias”** y **“Cómo leer tu app”** se base en **ejemplos estáticos**?
- ¿Querés usar **JS/HTMX** para:
  - Desplegar explicaciones de campo METAR/TAF al clicar.
  - Mostrar tooltip de “chance” sobre cada tipo de nube.  
- ¿Querés dejar un **modo “experto”** (con más detalles técnicos) o mantener todo en **lenguaje simple**?

---

## 8. Road‑map derivado (ampliado)

Ahora, con tres ejes claros, podrás elegir el orden de avance:

### 8.1. V.1: Lluvias mejorada (contenido estático)

- ✔️ Subpágina “Lluvias” con:
  - Tabla de intensidad de lluvia por nube.
  - Sección de “Granizo, downburst, mammatus” en lenguaje simple.
  - Bloque de “probabilidades / chances” y recomendaciones prácticas.
- ✔️ Link desde el footer o desde la barra de navegación principal, usando el mismo estilo de botón que el resto del menú.
- ✔️ Único archivo estático (`src/Lluvias.html`) sin backend ni dependencias externas, integrado en el flujo de Vercel con tu `vercel.json` existente.

### 8.2. V.2: Interacción ligera en “Lluvias”

- ✔️ Mini‑ejercicios guiados:
  - “¿Qué tipo de lluvia esperar si ves esta nube?”
  - “¿Qué acción tomarías si ves mammatus?”.
- ✔️ Usar HTML/CSS estático con un toque de JS/HTMX para:
  - Desplegar explicaciones de cada fenómeno al clicar.
  - Reforzar la idea de “chance” o “probabilidad” según el tipo de nube.

### 8.3. V.3: Lluvias + METAR/TAF + modelo de tu celular

- ✔️ Página de “Lluvias” conectada conceptualmente con:
  - La sección “Aeronáutico: METAR & TAF”.
  - Un bloque de “Cómo entender tu app de clima” (modelo de tu celular).
- ✔️ Comparación simple:
  - “Esto que ves en el cielo es lo mismo que la app llama X.”
  - “Este tipo de lluvia se refleja como Y en un METAR/TAF.”

### 8.4. V.4: Radar y satélite explicados en pocas palabras

- ✔️ Bloque específico:
  - “Cómo leer una app de radar o de imagen satelital en pocas palabras”.
- ✔️ Enfoque:
  - Significado de colores y tonos.
  - Movimiento de tormentas.
  - Qué decisiones tomar (posponer vuelo, buscar refugio, revisar el pronóstico oficial).

### 8.5. Ajuste en función del estado actual

Hoy, la sección **“Aeronáutico”** no es una página de contenidos, sino un **botón de filtro** en la barra de navegación que filtra ciertas nubes con el comportamiento `filterCards('aero', this)`.

Antes de avanzar con el desarrollo de la sección **“Aeronáutico: METAR & TAF”**, se propone:

- Dejar el botón “Aeronáutico” **tal cual**, como filtro interno de nubes, sin modificar su funcionalidad actual.
- Crear, en paralelo:
  - La subpágina `Lluvias.html` (ya implementada).
  - Una nueva subpágina `Aeronautico.html` o `metar-taf.html`, dedicada a la enseñanza de METAR/TAF.
- Añadir en la barra de navegación un **nuevo enlace**, no un nuevo botón de filtro:

  ```html
  <a href="/Aeronautico.html" class="fbtn ...">✈️ METAR & TAF</a>
  ```

De esta forma:
- La experiencia de filtrado existente se mantiene intacta.
- La nueva sección de **METAR & TAF** se introduce como un **bloque educativo** aparte, accesible desde el menú principal.

---

## 9. Footer consistente y actualizado

Con el footer actual, tu firma integrada y el año actualizado, queda así:

```html
<!-- ════ FOOTER ════ -->
<footer class="relative z-10 text-center px-6 py-8 border-t border-[#1c3358] text-[.67rem] text-slate-600 leading-">[1]
  Imágenes: <a class="underline hover:text-slate-400 transition-colors" href="https://commons.wikimedia.org" target="_blank" rel="noopener">Wikimedia Commons</a> bajo licencias Creative Commons ·
  Clasificación basada en el <a class="underline hover:text-slate-400 transition-colors" href="https://cloudatlas.wmo.int" target="_blank" rel="noopener">Atlas Internacional de Nubes (OMM)</a><br>
  Información aeronáutica con fines divulgativos — consultar documentación oficial OACI/ANAC para operaciones reales.<br>
  <span class="text-slate-500 mt-1">
    Creado por Francisco A. · <a class="underline hover:text-slate-400 transition-colors" href="https://ajconsultingitwebv2.vercel.app/">ajconsultingitwebv2.vercel.app</a> · 2026 ©
  </span>
</footer>
```

## 10. Plan de evaluación: integración de METAR y TAF reales usando una API

Este plan está pensado para **evaluar** si conviene, cómo y con qué restricciones usar una API de METAR/TAF real en SkyPulse, **sin escribir código todavía**.

---

### 10.1. Objetivo de la evaluación

- Decidir **si vale la pena** usar METAR/TAF en tiempo real frente a ejemplos estáticos.
- Elegir **qué API** encaja mejor con:
  - Tu stack (HTML/CSS/JS estático, Tailwind, Vercel).
  - Tus límites de recursos (sin backend, solo frontend).
  - Tu modelo de negocio (gratis vs. pago).
- Definir **cómo se va a usar** la API:
  - Sólo para mostrar el texto.
  - O también para análisis ligero (VFR/IFR, recomendaciones).
- Anticipar **riesgos técnicos**:
  - Fallos de API, rate limits, cambios de formato, etc.

---

### 10.2. Criterios de evaluación de la API

Para cada API que consideres (por ejemplo: CheckWX, Avwx, Aviation Weather Center, etc.), evaluá:

- **Acceso y costo**:
  - ¿Es completamente gratuita?
  - ¿Hay un plan gratuito con límite de requests?
  - ¿Requiere registro, clave de API, y cómo se gestiona?
- **Formato de respuesta**:
  - ¿Te devuelve METAR/TAF como **texto plano** o como **JSON estructurado**?
  - ¿Es fácil de parsear en el lado del cliente sin backend?
- **Límites de uso**:
  - ¿Cuántos requests por minuto/por día permiten?
  - ¿Qué pasa si excedés? (429, message de error, etc.)
- **Estabilidad y documentación**:
  - ¿La documentación es clara y actualizada?
  - ¿La API cambia de formato frecuentemente?
- **Dependencia de terceros**:
  - ¿Qué pasa si la API se cae o cambia de modelo de negocio?
  - ¿Es razonable que tu producto crítico dependa de ella?

---

### 10.3. Flujo de datos propuesto (a evaluar)

Antes de implementar, define el **flujo conceptual** que luego se traducirá en código:

- **Entrada del usuario**:
  - ¿Va a ingresar un **ICAO** (ej. AEP, EZE, LAX)?
  - ¿O prefieres que siempre muestres el METAR/TAF de un aeropuerto fijo (por ejemplo, tu aeropuerto local)?
- **Llamada a la API**:
  - ¿Usarás **fetch** desde el frontend (puro JS) o dejarás un **proxy ligero** (por ejemplo, FastAPI mínimo en Vercel/Render)?
  - ¿Cómo manejarás la **clave de API** (visible en el frontend, guardada en variables de entorno, etc.)?
- **Tratamiento de la respuesta**:
  - ¿Solo mostrarás el **texto tal cual**?
  - ¿O harás un **parsing ligero** del METAR/TAF para resaltar:
    - Viento.
    - Visibilidad.
    - Nubes.
    - Fenómenos (CB, TS, GR, etc.)?
- **Caché y performance**:
  - ¿Vas a **cachear resultados** (por ejemplo, 10 minutos) para reducir llamadas innecesarias?
  - ¿Cómo manejarás el **cambio de tiempo real** (por ejemplo, actualizar cada X minutos sin romper el límite de requests)?

---

### 10.4. Integración con la experiencia de usuario

Antes de implementar, define **cómo querés que la API se sienta para el usuario**:

- **Propuesta A: “Leer tu METAR real”**  
  - El usuario entra en la sección “Aeronáutico: METAR & TAF”.
  - Ve una explicación educativa de cada campo.
  - Luego tiene un campo para **ingresar el ICAO**.
  - Al clicar “Cargar METAR & TAF”, se llama a la API y se muestra el texto.
  - Opcionalmente, se resaltan o explican secciones del texto.

- **Propuesta B: “Aprender con ejemplos estáticos”**  
  - El contenido educativo sigue siendo igual.
  - No hay llamada a API, solo ejemplos sintéticos.
  - Solo más adelante, si conviene, se añade la parte de “prueba con tu aeropuerto”.

Debes decidir:

- ¿Querés que la **experiencia principal** sea:
  - **Educativa** (enseñar cómo leer) o
  - **Funcional** (mostrar el METAR real de tu aeropuerto)?

---

### 10.5. Evaluación de riesgos y trade‑offs

Antes de pasar a la implementación, responde a estas preguntas:

- **Confiabilidad**:
  - ¿Estás dispuesto a que, si la API falla, el usuario vea:
    - Un mensaje de error.
    - O un conjunto de ejemplos estáticos como fallback?
- **Costo y escalabilidad**:
  - ¿Qué pasaría si SkyPulse empieza a tener varios cientos de usuarios al día?
  - ¿Las cuotas de la API gratis serán suficientes?
- **Seguridad**:
  - ¿Es aceptable tener la **clave de API visible en el frontend**?
  - ¿O prefieres un **proxy mínimo** (por ejemplo, FastAPI en Vercel) que esconda la clave?
- **Mantenimiento**:
  - ¿Qué tan fácil será cambiar de API si la actual deja de funcionar o cambia el formato?
  - ¿Tienes un plan B (por ejemplo, cambiar a otra API o volver a ejemplos estáticos)?

---

### 10.6. KPIs de evaluación

Para decidir si integrar la API, define métricas simples:

- **Rendimiento**:
  - Tiempo de carga del METAR/TAF (desde que el usuario hace clic hasta que ve el texto).
- **Tasa de errores**:
  - ¿Cuántas veces falla la API?
- **Recursos**:
  - Número de requests por día (para ver si se acerca al límite gratuito).
- **Experiencia de usuario**:
  - ¿Los usuarios encuentran útil ver el METAR/TAF real de su aeropuerto?
  - ¿O prefieren ejemplos más simples?

---

### 10.7. Decisiones previas a la implementación

Antes de escribir cualquier línea de código, deberías tener claras:

- ¿Qué **API** elijo y **por qué**?  
- ¿Qué **caso de uso** principal quiero:  
  - solo enseñar a leer,  
  - o también mostrar METAR/TAF reales?  
- ¿Qué **trade‑off** estoy dispuesto a aceptar:
  - velocidad vs. confiabilidad,
  - simplicidad vs. funcionalidad.

Una vez que tengas eso definido, podrás avanzar a la **implementación**, que será solo un **reflejo técnico** de esas decisiones.

---

## 11. Plan de anti‑hardcodeo de información sensible

Este plan define cómo **evitar hardcodear credenciales y configuraciones sensibles** (claves de API, URLs internas, tokens, etc.) en el código fuente, especialmente en proyectos estáticos como SkyPulse.

---

### 11.1. Objetivo

- Minimizar el **riesgo de exposición accidental** de:
  - Claves de API.
  - URLs de servicios internos.
  - Configuraciones privadas.  
- Preparar el proyecto para un eventual **paso a un backend ligero** (por ejemplo, FastAPI/Render) sin tener que reescribir toda la lógica de secretos.  
- Mantener el **límite de 512 MB de RAM** y el modelo de despliegue actual (Vercel, HTML estático).

---

### 11.2. Prácticas actuales a evitar

Antes de definir cómo hacerlo bien, identifica qué situaciones representan **hardcode** en tu contexto:

- **Claves de API escritas directamente en JS**:

  ```js
  const API_KEY = "tu_clave_muy_larga_y_secreta";
  ```

- **URLs de APIs sensibles o internas**:

  ```js
  const API_BASE = "https://mi‑servidor‑interno.com/api";
  ```

- **Valores de configuración críticos**:

  - Límites de rate‑limit, endpoints admin, etc., en strings dentro del HTML/JS.

---

### 11.3. Reglas de “anti‑hardcodeo” para el frontend estático

Mientras el proyecto siga siendo **solo frontend estático** (sin backend):

- **Regla 1: No hay secretos “reales” en el cliente**  
  - Cualquier clave de API que esté en el navegador **se asume pública** (aunque esté empaquetada en JS o minificada).  
  - Eso implica que **no deberías usar claves de servicios privados** (por ejemplo, bases de datos, auth backend, etc.) en el frontend.

- **Regla 2: Claves de API de recursos públicos bien documentados**  
  - Si el servicio (por ejemplo, una API de METAR/TAF pública como CheckWX, Avwx, etc.) **ya está pensada para usarse en el frontend** (y permite que la clave viaje con tus peticiones), aceptarlo como “clave tolerablemente pública”.  
  - En ese caso, el enfoque cambia de “esconder” a “limitar el uso” (rate‑limit en la propia API, restricción por dominio, etc.).

- **Regla 3: No guardar nada sensible en localStorage/sessionStorage**  
  - Tokens, cookies, claves, etc., no se guardan en el cliente directamente.  
  - Si el proyecto evoluciona hacia autenticación, eso se resolverá en un backend (por ejemplo, FastAPI/Supabase) con cookies HttpOnly/Secure o tokens de corta duración.

- **Regla 4: Usar variables de entorno solo en el lado del servidor**  
  - Si el día de mañana añadís un backend ligero (FastAPI, Supabase, etc.), todas las claves quedan en **variables de entorno** del despliegue (Vercel, Render, etc.).  
  - El frontend **no conoce las claves**, solo llama a un endpoint de tu backend que ya las usa internamente.

---

### 11.4. Estructura de configuración recomendada

Aunque el proyecto hoy sea estático, preparalo con mentalidad de “future‑proving”:

- **Archivos de configuración dedicados** (no código de producción):  
  - `config/defaults.js` o `config/`:  
    - URLs base públicas.  
    - Flags de features (ej. “enable_mock_api”, “exclude_real_api_for_now”).  
  - Esos archivos se pueden versionar, pero **no incluyen claves**.
- **Claves de API reales**:
  - Siempre que sea posible, las claves de API de terceros que requieran protección:
    - Se mantienen **fuera del código fuente**.
    - Se almacenan en **variables de entorno** del backend cuando lo tengas.
- **Mock de servicios**:
  - Mientras el backend no exista, usá:
    - Datos estáticos en el frontend para la parte educativa.
    - O una **API de prueba pública** con clave pública o fácil de regenerar.

---

### 11.5. Flujo de datos y seguridad propuesto

Define un flujo seguro para el futuro:

- **Hoy (frontend estático)**:
  - Si usás una API de METAR/TAF pública:
    - Aceptá su **modelo de “clave pública en el frontend”** como parte de su diseño.  
    - Asegurate de que el servicio limite por dominio y rate (por ejemplo, 100 peticiones por minuto).

- **Cuando tengás un backend ligero** (por ejemplo, FastAPI en Vercel/Render):
  - El frontend **no llama directamente a la API de METAR/TAF**, sino a tu backend:
    - `GET /api/metar/ICAO`
    - `GET /api/taf/ICAO`
  - El backend, en su entorno, tiene la clave de la API en **variables de entorno**.  
  - El frontend recibe **solo los datos, nunca la clave**.

Flujo ideal:

1. Usuario hace clic en “Cargar METAR”.
2. Frontend llama a `https://tu‑backend.vercel.app/api/metar/AEP`.
3. Backend hace:
   - `GET https://api.externo.com/metar/AEP?key=variable_de_entorno`.
4. Backend devuelve:
   - `200 OK { metar: "..." }`.
5. Frontend muestra el METAR.

---

### 11.6. KPIs de seguridad y de “anti‑hardcodeo”

Para medir que tu estrategia de seguridad está bien, define:

- **No humanos deberían poder usar tu clave de API** si cambias proveedor o la revocas.  
- **El código fuente público** (GitHub, etc.) **no debe contener**:
  - Claves de API de servicios privados.
  - URLs de endpoints de autenticación o de datos internos.
- **Si el proyecto evoluciona**, el número de “hardcodes” en el frontend debe tender a **cero** (salvo excepciones documentadas, ej. “clave pública de API de METAR/TAF”).

---

### 11.7. Checklist de anti‑hardcodeo para tu contexto actual

Antes de implementar algo que use APIs o datos sensibles, asegurate de que:

- ☐ **No hay claves de API de backend, auth, bases de datos o similares** en el código del navegador.  
- ☐ Cualquier **clave de API de terceros** que sí esté en el frontend:
  - Pertenece a un servicio cuyo **modelo de uso** permite que viaje en el frontend.  
  - Está protegido por ratelimit y, si es posible, restricción por dominio.
- ☐ Si el proyecto necesita autenticación o datos privados, está **planeado**:
  - Que el backend haga de intermediario.
  - Que las claves vivan en variables de entorno del backend.
- ☐ Los **datos sensibles** (tokens, sesiones, etc.) **no se guardan en localStorage/sessionStorage**.

---

Francisco A.  
[ajconsultingitwebv2.vercel.app](https://ajconsultingitwebv2.vercel.app/)  
🟢 2026 ©