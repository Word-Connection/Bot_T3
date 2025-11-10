# 📋 Documentación: Updates Parciales (WebSocket) al Frontend

Esta documentación describe todos los updates parciales que se envían al frontend mediante WebSocket durante la ejecución de los diferentes caminos de automatización.

---

## 📚 Índice

1. [Camino C - Deudas](#camino-c---deudas)
2. [Camino B - Movimientos](#camino-b---movimientos)
3. [Camino D - PIN](#camino-d---pin)
4. [Resumen y Flujos](#resumen-y-flujos)

---

## 🔷 CAMINO C - Deudas (deudas.py)

### Estructura Base
Todos los updates del Camino C incluyen estos campos base:
```json
{
  "dni": "string",
  "score": "string",
  "etapa": "string",
  "info": "string",
  "admin_mode": boolean,
  "timestamp": number
}
```

---

### 1. Update: **Iniciando**

**Cuándo se envía**: Al comenzar el análisis del cliente

```json
{
  "dni": "32033086",
  "score": "",
  "etapa": "iniciando",
  "info": "Iniciando análisis de cliente",
  "admin_mode": false,
  "timestamp": 1762550400000
}
```

**Campos**:
- `score`: Vacío al inicio
- `etapa`: `"iniciando"`
- `info`: Mensaje descriptivo del inicio

---

### 2. Update: **Obteniendo Score**

**Cuándo se envía**: Antes de ejecutar el Camino C

```json
{
  "dni": "32033086",
  "score": "",
  "etapa": "obteniendo_score",
  "info": "Analizando información del cliente",
  "admin_mode": false,
  "timestamp": 1762550402000
}
```

**Campos**:
- `score`: Aún vacío
- `etapa`: `"obteniendo_score"`
- `info`: Indica que está analizando

---

### 3. Update: **Score Obtenido** ⭐ (CON IMAGEN)

**Cuándo se envía**: Después de que Camino C obtiene el score

```json
{
  "dni": "32033086",
  "score": "351",
  "etapa": "score_obtenido",
  "info": "Score: 351",
  "admin_mode": false,
  "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
  "timestamp": 1762550428647
}
```

**Campos especiales**:
- `score`: Valor numérico del score (string)
- `etapa`: `"score_obtenido"`
- `image`: 📸 **Imagen en base64** de la captura del score
- `timestamp`: Timestamp del archivo de captura

**Nota importante**: ⚠️ **Esta es la única forma de obtener la imagen del score**. La imagen NO se incluye en el JSON final.

---

### 4. Update: **Buscando Deudas** (Condicional)

**Cuándo se envía**: Solo si el score está entre 80-89 O si `admin_mode=true`

```json
{
  "dni": "32033086",
  "score": "85",
  "etapa": "buscando_deudas",
  "info": "Extrayendo información de deudas",
  "admin_mode": true,
  "timestamp": 1762550430000
}
```

**Campos**:
- `score`: Ya tiene el valor obtenido
- `etapa`: `"buscando_deudas"`
- `info`: Indica que ejecutará Camino A

**Condición**: Este update NO se envía si el score < 80 o > 89 (a menos que `admin_mode=true`)

---

### 5. Update: **Extracción Completada** (Condicional)

**Cuándo se envía**: Solo si se ejecutó Camino A y terminó exitosamente

```json
{
  "dni": "32033086",
  "score": "85",
  "etapa": "extraccion_completada",
  "info": "Procesando información de deudas",
  "admin_mode": true,
  "timestamp": 1762550500000
}
```

**Campos**:
- `etapa`: `"extraccion_completada"`
- `info`: Indica que Camino A terminó

---

### 6. Update: **Datos Listos** (Final)

**Cuándo se envía**: Al finalizar todo el proceso, antes de enviar el JSON final

```json
{
  "dni": "32033086",
  "score": "351",
  "etapa": "datos_listos",
  "info": "Consulta finalizada",
  "admin_mode": false,
  "has_deudas": true,
  "success": true,
  "timestamp": 1762550505000
}
```

**Campos especiales**:
- `etapa`: `"datos_listos"`
- `has_deudas`: Indica si se encontraron deudas (boolean)
- `success`: Indica si la consulta fue exitosa (boolean)

---

### 7. Update: **Error - Timeout**

**Cuándo se envía**: Si Camino C tarda más de 120 segundos

```json
{
  "dni": "32033086",
  "score": "",
  "etapa": "error_analisis",
  "info": "Timeout ejecutando Camino C",
  "admin_mode": false,
  "timestamp": 1762550420000
}
```

**Campos**:
- `etapa`: `"error_analisis"`
- `info`: Describe el error de timeout

---

### 8. Update: **Error - Análisis**

**Cuándo se envía**: Si Camino C falla con error (returncode != 0)

```json
{
  "dni": "32033086",
  "score": "",
  "etapa": "error_analisis",
  "info": "Error al analizar la información del cliente",
  "admin_mode": false,
  "timestamp": 1762550425000
}
```

**Campos**:
- `etapa`: `"error_analisis"`
- `info`: Mensaje genérico de error

---

## 🔶 CAMINO B - Movimientos (movimientos.py)

### Estructura Base
Todos los updates del Camino B incluyen estos campos base:
```json
{
  "dni": "string",
  "etapa": "string",
  "info": "string",
  "timestamp": number
}
```

**Nota**: Camino B NO incluye campo `score` ni `admin_mode`

---

### 1. Update: **Línea Procesada** (Múltiple)

**Cuándo se envía**: Por cada línea telefónica que tiene movimientos activos

```json
{
  "dni": "32033086",
  "etapa": "linea_procesada",
  "info": "Línea 123456789: 5 movimiento(s) - Último: 2025-11-10 14:30...",
  "service_id": "123456789",
  "count": 5,
  "ultimo": "2025-11-10 14:30 - Llamada saliente a 1145678901...",
  "timestamp": 1762550450000
}
```

**Campos especiales**:
- `etapa`: `"linea_procesada"`
- `service_id`: ID de la línea telefónica procesada
- `count`: Cantidad de movimientos encontrados en esa línea
- `ultimo`: Preview del último movimiento (truncado a 60 chars)

**Frecuencia**: Se envía N veces (una por cada línea con movimientos)

---

### 2. Update: **Completado con Movimientos**

**Cuándo se envía**: Al finalizar el procesamiento, si se encontraron movimientos

```json
{
  "dni": "32033086",
  "etapa": "completado",
  "info": "25 movimientos encontrados en 3 líneas",
  "total_movimientos": 25,
  "total_lineas": 3,
  "timestamp": 1762550480000
}
```

**Campos especiales**:
- `etapa`: `"completado"`
- `total_movimientos`: Total de movimientos encontrados
- `total_lineas`: Total de líneas procesadas

---

### 3. Update: **Completado sin Movimientos**

**Cuándo se envía**: Al finalizar el procesamiento, si NO se encontraron movimientos

```json
{
  "dni": "32033086",
  "etapa": "completado",
  "info": "Sin movimientos activos",
  "total_movimientos": 0,
  "total_lineas": 2,
  "timestamp": 1762550480000
}
```

**Campos especiales**:
- `etapa`: `"completado"`
- `total_movimientos`: 0
- `total_lineas`: Total de líneas procesadas (aunque no tengan movimientos)

---

### 4. Update: **Error - Timeout**

**Cuándo se envía**: Si el proceso tarda más de 600 segundos

```json
{
  "dni": "32033086",
  "etapa": "error",
  "info": "Timeout: El proceso tardó demasiado tiempo",
  "timestamp": 1762550490000
}
```

**Campos**:
- `etapa`: `"error"`
- `info`: Describe el error de timeout

---

### 5. Update: **Error - Python no encontrado**

**Cuándo se envía**: Si no encuentra el ejecutable de Python

```json
{
  "dni": "32033086",
  "etapa": "error",
  "info": "Error: No se encuentra Python del venv",
  "timestamp": 1762550485000
}
```

---

### 6. Update: **Error - Genérico**

**Cuándo se envía**: Para cualquier otro error durante la ejecución

```json
{
  "dni": "32033086",
  "etapa": "error",
  "info": "Error al procesar movimientos: [mensaje de error]",
  "timestamp": 1762550495000
}
```

---

## 🔵 CAMINO D - PIN (pin.py)

**⚠️ NO TIENE UPDATES PARCIALES**

El Camino D (PIN) no envía updates parciales durante la ejecución. Solo retorna el JSON final cuando termina.

**Razón**: El proceso de cambio de PIN es muy rápido y no requiere feedback intermedio.

---

## 📊 Resumen por Camino

### Tabla Comparativa

| Camino | Total Updates | Con Imagen | Con Extra Data | Condicionales |
|--------|--------------|------------|----------------|---------------|
| **C (Deudas)** | 6-8 updates | 1 (score_obtenido) | 2 (score_obtenido, datos_listos) | 2 (buscando_deudas, extraccion_completada) |
| **B (Movimientos)** | N+1 updates | 0 | N+1 (todas) | 0 |
| **D (PIN)** | 0 updates | 0 | 0 | 0 |

### Explicación

- **Camino C**: Entre 6 y 8 updates dependiendo de si se ejecuta Camino A
  - 6 updates: Flujo mínimo (sin Camino A)
  - 8 updates: Flujo completo (con Camino A)

- **Camino B**: N+1 updates donde N es el número de líneas con movimientos
  - Ejemplo: 3 líneas con movimientos = 4 updates (3 linea_procesada + 1 completado)

- **Camino D**: No envía updates parciales

---

## 🎯 Flujos Típicos Completos

### Flujo 1: Deudas - Score Bajo (< 80)

```
1. iniciando
2. obteniendo_score
3. score_obtenido (con imagen)
4. datos_listos
```

**Total**: 4 updates

---

### Flujo 2: Deudas - Score Alto (80-89)

```
1. iniciando
2. obteniendo_score
3. score_obtenido (con imagen)
4. buscando_deudas
5. extraccion_completada
6. datos_listos
```

**Total**: 6 updates

---

### Flujo 3: Deudas - Modo Admin (cualquier score)

```
1. iniciando
2. obteniendo_score
3. score_obtenido (con imagen)
4. buscando_deudas (forzado por admin_mode)
5. extraccion_completada
6. datos_listos
```

**Total**: 6 updates

---

### Flujo 4: Deudas - Error en Camino C

```
1. iniciando
2. obteniendo_score
3. error_analisis
```

**Total**: 3 updates

---

### Flujo 5: Movimientos - Con 3 líneas

```
1. linea_procesada (línea 1)
2. linea_procesada (línea 2)
3. linea_procesada (línea 3)
4. completado
```

**Total**: 4 updates

---

### Flujo 6: Movimientos - Sin movimientos

```
1. completado (total_movimientos: 0)
```

**Total**: 1 update

---

## 🔍 Campos Especiales Importantes

### `image` (solo en score_obtenido)

**Formato**: `"data:image/jpeg;base64,/9j/4AAQSkZJRg..."`

**Descripción**: Imagen en base64 de la captura de pantalla del score.

**Importante**: 
- ⚠️ Esta es la **ÚNICA** forma de obtener la imagen del score
- La imagen NO se incluye en el JSON final
- El frontend debe capturar y guardar esta imagen del update `score_obtenido`

---

### `has_deudas` (solo en datos_listos)

**Valores posibles**: `true` | `false`

**Descripción**: Indica si se ejecutó Camino A y se encontraron deudas.

**Lógica**:
```javascript
has_deudas = final_camino_a && (
  final_camino_a.fa_actual.length > 0 || 
  final_camino_a.cuenta_financiera.length > 0
)
```

---

### `admin_mode` (Camino C)

**Valores posibles**: `true` | `false`

**Descripción**: Indica si el proceso se ejecutó en modo administrativo.

**Efecto**: 
- Si `admin_mode=true`, se ejecuta Camino A independientemente del score
- Si `admin_mode=false`, solo se ejecuta Camino A si score entre 80-89

---

### `service_id` (Camino B)

**Formato**: String numérico (ej: `"123456789"`)

**Descripción**: ID de la línea telefónica procesada.

**Uso**: Permite al frontend mostrar progreso por línea individual.

---

## 💡 Recomendaciones para el Frontend

### 1. Captura de Imagen

```javascript
// Capturar la imagen en el update score_obtenido
if (update.etapa === 'score_obtenido' && update.image) {
  saveScoreImage(update.dni, update.image);
}
```

### 2. Manejo de Progreso

```javascript
// Mostrar progreso según la etapa
const etapaMessages = {
  'iniciando': 'Iniciando análisis...',
  'obteniendo_score': 'Obteniendo score del cliente...',
  'score_obtenido': 'Score obtenido',
  'buscando_deudas': 'Buscando información de deudas...',
  'extraccion_completada': 'Extracción completada',
  'datos_listos': 'Consulta finalizada'
};
```

### 3. Detección de Deudas

```javascript
// En el update datos_listos
if (update.etapa === 'datos_listos') {
  if (update.has_deudas) {
    showDeudasSection();
  } else {
    hideDeudasSection();
  }
}
```

### 4. Contador de Movimientos (Camino B)

```javascript
// Acumular movimientos por línea
let totalMovimientos = 0;
let lineasProcesadas = 0;

if (update.etapa === 'linea_procesada') {
  totalMovimientos += update.count;
  lineasProcesadas++;
  updateProgress(lineasProcesadas, update.service_id);
}

if (update.etapa === 'completado') {
  showFinalResult(update.total_movimientos, update.total_lineas);
}
```

---

## 🐛 Manejo de Errores

### Tipos de Error

| Camino | Etapa Error | Descripción |
|--------|------------|-------------|
| C | `error_analisis` | Error al ejecutar Camino C o timeout |
| B | `error` | Cualquier error en Camino B |

### Ejemplo de Manejo

```javascript
if (update.etapa === 'error_analisis' || update.etapa === 'error') {
  showError(update.info);
  stopProcessing();
}
```

---

## 📝 Notas Técnicas

### Formato de Timestamps

- Todos los timestamps son en **milisegundos** desde epoch Unix
- Formato: `int(time.time() * 1000)`
- Ejemplo: `1762550428647`

### Orden de Envío

Los updates se envían en el orden documentado arriba. El frontend puede confiar en este orden para la lógica de progreso.

### Encoding

Todos los JSON se envían con `ensure_ascii=False` para soportar caracteres UTF-8 correctamente.

---

## 🔗 Referencias

- Archivo fuente Camino C: `Workers-T3/scripts/deudas.py`
- Archivo fuente Camino B: `Workers-T3/scripts/movimientos.py`
- Archivo fuente Camino D: `Workers-T3/scripts/pin.py`
- Worker principal: `Workers-T3/worker.py`

---

**Última actualización**: 10 de Noviembre, 2025
