"""El glosario de Mora: una definición corta por cada término que el enrutador sabe pedir (`TERMINOS_GLOSARIO`).

Es un dato estático del backend: no hace red ni lee ninguna caché. `FuentesDeCache` lo entrega entero y la hoja filtra por
los términos que nombró la pregunta (`hoja_datos._glosario`), así que acá no hay lógica.

Reglas de cada definición (las fija `tests/asistente/test_glosario.py`):
- cabe entera en la hoja (hasta 200 caracteres: más largo, la hoja la cortaría a la mitad);
- una sola oración, sin cifras (el verificador coteja las cifras de la respuesta contra los datos de la hoja), sin números
  en letras, sin Markdown ni enlaces, sin alarmismo y sin nombrar proveedores;
- una definición es siempre general: no afirma qué pasa HOY. Para eso están los datos y los avisos del SMN.

Las 13 nubes y fenómenos que también explica la web (`apps/frontend/src/data/clouds.ts`) tienen aquí una versión más corta
con las mismas ideas; el test compara los `id` de `clouds.ts` con este glosario para que una nube nueva no quede sin explicar.
Los textos son un BORRADOR que el dueño aprobó el 2026-10-17: cambiar una frase es tocar este archivo.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

GLOSARIO: Mapping[str, str] = MappingProxyType({
    "cirro": (
        "Nube alta de hielo, en filamentos finos y blancos como pinceladas. Con buen tiempo no avisa nada, pero si se "
        "espesan y bajan puede venir un cambio."
    ),
    "cirrocumulo": (
        "Nube alta en pequeñas motas blancas ordenadas en filas, como escamas. Dura muy poco y suele convertirse en "
        "cirros o cirrostratos."
    ),
    "cirrostrato": (
        "Velo blanquecino y alto que cubre el cielo. Alrededor del sol o de la luna forma un halo, y suele anunciar "
        "lluvia en las próximas horas."
    ),
    "cumulo": (
        "Nube de algodón, de base plana y tope redondeado, que se forma con el calor del día. Las chicas son de buen "
        "tiempo; si crecen mucho, pueden ser tormenta."
    ),
    "cumulonimbo": (
        "Nube de tormenta muy alta y cargada. Puede traer lluvia fuerte, granizo, rayos y ráfagas de viento."
    ),
    "altocumulo": (
        "Parches y rollos grises y blancos a media altura. Los castellanus, con torrecitas, son el aviso clásico de "
        "una tormenta por la tarde."
    ),
    "altoestrato": (
        "Capa gris azulada a media altura que cubre el cielo: el sol se ve borroso, como detrás de un vidrio "
        "esmerilado. Suele venir antes de lluvia continua."
    ),
    "estrato": (
        "Capa baja, gris y pareja, como una niebla que no toca el suelo. Puede dejar llovizna fina, pero no lluvia "
        "fuerte."
    ),
    "estratocumulo": (
        "Capa baja de rollos o bloques grises y blancos, con claros entre medio. Es muy común y rara vez trae más "
        "que una llovizna."
    ),
    "nimboestrato": (
        "Capa gruesa, oscura y baja que tapa el sol. Trae lluvia o nieve continua y pareja, durante horas."
    ),
    "nimbo": (
        "Palabra que indica una nube que precipita: el nimboestrato da lluvia continua y el cumulonimbo, tormenta."
    ),
    "lenticular": (
        "Nube lisa, con forma de lente o de plato, que se queda quieta cerca de las montañas donde el viento fuerte "
        "forma ondas. Señala viento y turbulencia en altura."
    ),
    "mammatus": (
        "Bolsas que cuelgan bajo la base de un cumulonimbo, como ubres. Se asocian a tormentas fuertes, aunque por sí "
        "solas no significan que el tiempo empeore."
    ),
    "virga": (
        "Estelas de lluvia o de nieve que caen de una nube y se evaporan antes de llegar al suelo, como cortinas "
        "colgadas."
    ),
    "cape": (
        "Energía disponible para que el aire suba y se formen tormentas. Cuanto mayor es, más fuertes pueden ser, si "
        "algo las dispara. Se mide en J/kg."
    ),
    "isobara": (
        "Línea de un mapa que une puntos con la misma presión atmosférica. Muy juntas indican viento fuerte; "
        "separadas, viento débil."
    ),
    "granizo": (
        "Bolitas o piedras de hielo que caen de una nube de tormenta. Pueden dañar cultivos, autos y techos."
    ),
    "rocio": (
        "Gotitas de agua que se forman sobre el pasto y las superficies cuando se enfrían de noche y el aire tiene "
        "mucha humedad."
    ),
    "helada": (
        "Descenso de la temperatura por debajo de cero grados, que puede dañar las plantas. Es más probable en noches "
        "despejadas y sin viento."
    ),
    "escarcha": (
        "Cristales de hielo blancos que cubren el pasto y las superficies cuando hay helada y el vapor de agua se "
        "congela directamente."
    ),
    "zonda": (
        "Viento cálido, seco y fuerte que baja de la cordillera hacia el este, típico de Cuyo. Sube la temperatura y "
        "baja la humedad."
    ),
    "niebla": (
        "Nube a ras del suelo que reduce la visibilidad a menos de un kilómetro."
    ),
})
