"""Umbrales de la regla de tormenta para alertas push (FRA-348 / FRA-351).

Es el ÚNICO lugar donde viven estos números: los fija el dueño del producto y
cualquier ajuste se hace acá. Ver `regla.py` para cómo se aplican.
"""

# Códigos WMO de tormenta de ECMWF: 95 tormenta, 96/99 con granizo (97 y 98 no
# son códigos WMO válidos para Open-Meteo, se incluyen por el rango 95-99 que
# usa también el reporte de Instagram).
CODIGOS_TORMENTA: frozenset[int] = frozenset(range(95, 100))

# Los códigos WMO de tormenta CON granizo: el único dato del modelo que permite decir «posible granizo»
# en el aviso. El CAPE alto solo no lo dice.
CODIGOS_GRANIZO: frozenset[int] = frozenset({96, 99})

# CAPE de ECMWF (J/kg) a partir del cual una hora cuenta como tormenta aunque
# el código del tiempo todavía no la marque.
CAPE_TORMENTA_J_KG: float = 2500.0

# Revisiones programadas (hora de Argentina). Las de HOY miran desde esa hora
# hasta la medianoche de hoy; la de la noche mira el día siguiente completo
# (00 a 24 h).
REVISIONES_HOY: tuple[int, ...] = (5, 7, 10, 13, 16, 19)
REVISION_MANANA: int = 21

# Franja en la que nunca se avisa (hora de Argentina): desde las 22 h hasta
# las 5 h. La revisión de las 5 h es la de quien sale a trabajar entre las 6 y las 7.
SILENCIO_DESDE_H: int = 22
SILENCIO_HASTA_H: int = 5

# Avisos oficiales del SMN (FRA-359, S7): la corrida de 30 min funciona las 24 h,
# pero en la misma franja de silencio solo se manda el aviso de ESTE nivel; un
# amarillo o naranja espera a la primera corrida de las 5 h. Lo decidió el dueño.
SMN_NIVEL_QUE_PASA_DE_NOCHE: str = "rojo"

# ---------------------------------------------------------------------------
# Lluvia persistente (PR 1: MODO SOMBRA, solo se cuenta y no se manda nada).
#
# PROVISORIOS: salen de un backtest de 9 días en un solo punto y con otro modelo que el de las alertas (informe
# `informe-alerta-de-lluvia-2026-10-16-noche`). Con "3 mm en 6 h y 70 %" habría avisado 1-2 veces por semana en
# Córdoba, las dos veces con lluvia real; las reglas de lluvia FUERTE en mm no avisan casi nunca y las de solo
# probabilidad avisan todos los días. El conteo `con_lluvia` del log sirve para confirmarlos con los datos reales de
# ECMWF antes de ajustarlos. Ver `regla.evaluar_lluvia`.
# ---------------------------------------------------------------------------

# Una ventana de lluvia son estas horas seguidas.
LLUVIA_VENTANA_HORAS: int = 6

# Milímetros acumulados en la ventana a partir de los cuales es "lluvia persistente".
LLUVIA_MM_VENTANA: float = 3.0

# Probabilidad de precipitación MEDIA de las horas de la ventana (porcentaje). Solo se exige cuando ECMWF la dio para
# todas las horas de la ventana.
LLUVIA_PROBABILIDAD_MEDIA_MINIMA: float = 70.0

# Sin probabilidad: una hora "con agua" es una de al menos estos mm, y hacen falta tantas horas con agua en la
# ventana (distingue la lluvia persistente de un chaparrón corto que junta los mm en dos horas).
LLUVIA_MM_HORA_CON_AGUA: float = 0.1
LLUVIA_HORAS_CON_AGUA_MINIMAS: int = 4
