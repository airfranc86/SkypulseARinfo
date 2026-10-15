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
