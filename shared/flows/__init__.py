"""Sub-flujos de UI reutilizables entre caminos.

Cada modulo expone funciones que reciben el dict maestro de coordenadas y
ejecutan un bloque concreto de interaccion con T3 (ej: entrar un DNI, copiar
la tabla de Ver Todos, validar si hay fraude, etc).

Los flows NO emiten marcadores al worker. Eso es responsabilidad del camino
que los orquesta (via shared.io_worker).
"""
