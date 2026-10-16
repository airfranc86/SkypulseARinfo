"""Asistente de Mora: el cerebro que decide qué datos entran, arma la hoja y verifica la respuesta.

Todo es puro (sin red, sin reloj propio, sin claves): recibe datos ya obtenidos. El modelo de lenguaje entra
solo a través del protocolo `Modelo`; las pruebas y el desarrollo local usan `ModeloFalso`.
"""
