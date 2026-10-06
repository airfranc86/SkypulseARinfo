# Reporte diario de Instagram (FRA-326)

Genera, para el día siguiente, los datos y el texto del reporte de **Córdoba, Buenos Aires (CABA) y Resistencia**:
una variante por ciudad (*Alerta* o *Estándar*), un único caption para las tres y la estructura de carpetas de
Drive y del respaldo. Corre fuera de `apps/` (no se despliega) y reutiliza la lógica del backend para que los
números coincidan con la fila de 7 días de la web.

## Cómo correrlo

Con el Python del entorno del backend, desde la raíz del repositorio:

```powershell
# Solo mira: imprime los datos y la variante de cada ciudad como JSON. No escribe nada ni avisa.
apps\backend\.venv\Scripts\python.exe scripts\instagram\generar_reporte.py --solo-datos

# Pasado mañana en vez de mañana (hora de Argentina)
apps\backend\.venv\Scripts\python.exe scripts\instagram\generar_reporte.py --solo-datos --dias 2

# Reporte completo (necesita config.local.json o --salida)
apps\backend\.venv\Scripts\python.exe scripts\instagram\generar_reporte.py
```

Opciones: `--dias 1|2` (por defecto 1), `--fecha AAAA-MM-DD` (reemplaza a `--dias`), `--solo-datos`, `--sin-aviso`,
`--salida RUTA` (raíz de salida para pruebas; reemplaza a `config.local.json`).
Códigos de salida: `0` ok, `1` error de datos, configuración, render o escritura (las demás ciudades y carpetas
siguen), `2` argumentos inválidos.

## Configuración local

Copiá `config.example.json` como `config.local.json` (está en `.gitignore`) y completá las carpetas:

- `drive_dir`: la carpeta sincronizada con Google Drive para escritorio. **Va vacía en el ejemplo a propósito**:
  la ruta es del equipo de cada persona y no se versiona. Mientras esté vacía, ese destino se omite con un aviso
  por stderr.
- `backup_dir`: el respaldo local (`G:\Developer\AgenciaAssests\MARKETING\SkyPulse\Instagram`).

Alcanza con una de las dos; si faltan las dos, el script termina con un error claro. No hay claves ni secretos.

## Qué guarda

```
<raíz>/SkyPulse_Instagram_Reports/AAAA/MM_Mes/Semana_NN/
    AAAA-MM-DD_Reporte_<Alerta|Estandar>_<Cordoba|CABA|Resistencia>.png
    AAAA-MM-DD_Caption_Instagram.txt
```

La fecha, el mes y la semana ISO son los del **día pronosticado** (el 6/10/2026 es `Semana_41`). Volver a correr
el mismo día sobrescribe los archivos (escritura atómica). Cerca de fin de año la semana ISO puede ser de otro
año: `2027-01-01` queda en `2027/01_Enero/Semana_53`.

## Reglas

- **Alerta** si la ráfaga máxima del día (ECMWF) es **>= 50 km/h** de cualquier dirección, o hay tormenta
  (código 95 a 99 o riesgo convectivo alto), o llueve **más de 15 mm**. Si no, **Estándar**.
- Jerarquía: alerta de viento (con de dónde viene), tormenta ("Tormenta fuerte posible, según el modelo", nunca un
  porcentaje de granizo), lluvia (probabilidad, mm y franja crítica) y, al final, máxima, mínima y cielo.
- Franja crítica de lluvia: la franja de 3 h con más lluvia (mínimo 0,1 mm) y las contiguas con al menos el 50 %
  de ese máximo, como `07:00 a 10:00 hs`. Para la franja de las ráfagas más fuertes se usa el 80 %.
- **De dónde sale cada dato de lluvia:** el total del día y la probabilidad, del ancla diaria ECMWF (como la web);
  los mm de cada franja de 3 h (que eligen la franja crítica), de **ECMWF horario** (`fuente_horaria_ecmwf.py`:
  una sola llamada extra a Open-Meteo por ciudad, `models=ecmwf_ifs025`, sin reintentos). Así total, probabilidad
  y franja son del mismo modelo. Lo demás de las franjas (ráfagas, probabilidad por franja, CAPE, temperatura)
  sigue saliendo del servicio horario del backend.
- **Coherencia y cota:** si la suma horaria ECMWF del día (00 a 24 h) se aleja del total diario más de **0,5 mm o el
  25 % del total** (lo que sea mayor), el propio ECMWF se contradice. Decisión del usuario: se muestra el **mayor
  de los dos como cota** ("hasta 29 mm", palabra que sale de `lluvia_texto.rain_summary`, igual en placa y
  caption) y la franja crítica se calcula con los mm horarios. Si la cota es la diaria, la franja solo se
  calcula cuando la suma horaria supera 0,9 mm. La regla de la variante Alerta (lluvia mayor a 15 mm) usa la
  cifra mostrada (`reglas.shown_rain_mm`). Si ECMWF horario no respondió, le faltan horas o el total no es de
  ECMWF: sin cota ni franja, y nunca se usa la lluvia de otro modelo. El motivo queda en el log y en el
  **resumen de avisos** al final de la corrida (una sola vez; y en `avisos` de `--solo-datos`); la placa no lo
  explica. La tolerancia absorbe la diferencia normal entre la serie horaria y la diaria de Open-Meteo (0,1 a
  0,8 mm en los días coherentes medidos) y atrapa un total que no describe las horas (Resistencia 7/10/2026:
  entre 1,8 y 2,4 mm diarios contra 17 a 29 mm horarios, según la corrida del modelo).
- **Texto de lluvia (placa y caption con la misma regla, `lluvia_texto.py`):** más de 0,9 mm → probabilidad, mm y
  franja crítica; hasta 0,9 mm con probabilidad mayor al 15 % → "poca cantidad"; si no, "Sin lluvia".
- El caption nunca nombra los modelos ni la fuente de datos: crédito `Datos: SkyPulse` y la leyenda de que no es un
  aviso oficial.

## Placas

Cada ciudad es una página HTML autocontenida (`plantillas/`: `placa.html`, `base.css`, `alerta.css`,
`estandar.css`) que Chrome o Edge sin interfaz convierten en un PNG de **1080×1920**. No hace falta internet: el
logo (`apps/frontend/public/Logo.png`) y los íconos del cielo (los Meteocons de la web) van embebidos.

- **Navegador:** se busca Chrome o Edge en las rutas habituales de Windows; para usar otro, poné su ruta completa
  en la variable de entorno `SKYPULSE_NAVEGADOR`. Si no hay ninguno, la ciudad falla con un error claro.
- **Zona segura:** todo lo importante queda entre los 250 px de arriba y los 340 px de abajo (la interfaz de
  Instagram), con 72 px a los costados; abajo solo va el crédito. Si alguna vez el contenido no entrara, la
  página lo achica en vez de cortarlo (`plantillas/ajuste.js`).
- **Tipografía:** la app usa DM Sans y Playfair Display desde Google Fonts. Para usarlas en las placas, copiá sus
  archivos (`.woff2`, `.ttf`…, por ejemplo `DMSans-Bold.ttf`, `PlayfairDisplay-SemiBold.ttf`) en
  `plantillas/fuentes/` y se embeben solas. Sin ellos se usan Segoe UI Variable y Sitka (de Windows).
- **Severidad escrita:** *Alerta* (rojo) para ráfagas de 50 km/h o más, tormenta o lluvia de más de 15 mm;
  *Atención* (ámbar) para la lluvia que no llega a la alerta. El color nunca es la única señal.

## Pruebas

```powershell
apps\backend\.venv\Scripts\python.exe -m pytest scripts\instagram\tests -q -p no:cacheprovider
```

Usan datos sintéticos: sin red, sin notificaciones reales y sin abrir el navegador, salvo las marcadas
`navegador`, que dibujan placas de verdad y miden que nada salga de la zona segura (se saltean si no hay Chrome
ni Edge; para correr solo esas: `-m navegador`).

## Qué falta

- **Programación diaria a las 19:00 (T4):** todavía no hay tarea en el Programador de tareas.
