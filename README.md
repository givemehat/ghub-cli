# ghub-cli

Interfaz de línea de comandos (CLI) para la API de `genomic-hub`. Permite consulta de metadatos, sincronización masiva desde NCBI, exportación formateada y descarga segura de secuencias (OTP).

Optimizado para personal técnico/operativo. Soporta lotes de hasta 120 IDs por operación, superando límites de la web.

## Estructura del Proyecto

```text
genomic-hub-cli/
├── pyproject.toml        # Empaquetado y dependencias. Registra comando `ghub`.
└── app/
    ├── cli.py             # Punto de entrada, definición de grupos y comandos Click.
    ├── core/
    │   ├── client.py      # Cliente HTTP delgado sobre la API.
    │   └── config.py      # Manejo de configuración persistente (~/.config/ghub-cli/).
    ├── commands/
    │   ├── check.py       # Verificar existencia local de IDs.
    │   ├── sync.py        # Sincronizar datos desde NCBI.
    │   ├── search.py      # Consultar datos locales.
    │   ├── explore.py     # Buscar BioProjects en NCBI (texto libre).
    │   ├── export.py      # Exportar metadatos (CSV/JSON).
    │   ├── download.py    # Descarga de secuencias (flujo OTP).
    │   └── interactive.py # Menú interactivo guiado (legacy).
    └── utils/             # Utilidades internas (formato, identificadores, etc.)

```

## Instalación

Requiere Python 3.8+.

```bash
cd genomic-hub-cli
pip install -e .

```

Esto instalará las dependencias necesarias y registrará el comando `ghub` en tu sistema.

## Opciones Globales

Estas opciones se aplican a **cualquier** comando de `ghub` y se colocan antes del subcomando.

| Opción | Descripción | Ejemplo de uso con bandera |
| --- | --- | --- |
| `--base-url TEXT` | Sobrescribe temporalmente la URL de la API. | `ghub --base-url http://localhost:8000 check PRJNA257197` |
| `--timeout INTEGER` | Tiempo de espera de red en segundos. | `ghub --timeout 60 search PRJNA257197` |

## Configuración Persistente

Gestiona la configuración guardada en `~/.config/ghub-cli/config.json`.

```bash
ghub config COMANDO [ARGUMENTOS]

```

### Comandos de Configuración

| Comando | Descripción | Ejemplo |
| --- | --- | --- |
| `set-url URL` | Guarda la URL base de la API. | `ghub config set-url https://api.genomichub.unam.mx` |
| `set-email EMAIL` | Valida y guarda el correo para descargas. | `ghub config set-email usuario@unam.mx` |
| `unset-email` | Olvida el correo guardado. | `ghub config unset-email` |
| `show` | Muestra la configuración actual. | `ghub config show` |

---

## Referencia de Comandos Principales

### `ghub check`

Verifica si IDs existen en Genomic Hub local. No consulta NCBI.

**Sintaxis:**

```bash
ghub check [IDS...] [OPCIONES]

```

**Opciones:**

| Opción | Descripción | Ejemplo de uso con bandera |
| --- | --- | --- |
| `--json` | Muestra la respuesta en formato JSON crudo. | `ghub check SRP045416 --json` |

### `ghub sync`

Sincroniza metadatos desde NCBI al servidor local. Necesario para IDs "Faltantes".

**Sintaxis:**

```bash
ghub sync [IDS...] [OPCIONES]

```

**Opciones:**

| Opción | Alias | Descripción | Ejemplo de uso con bandera |
| --- | --- | --- | --- |
| `--wait` | `-w` | Bloquea la terminal y muestra un spinner de progreso en tiempo real hasta que la sincronización finalice en el servidor. | `ghub sync PRJNA257197 --wait` |
| `--json` | | Muestra la respuesta inicial de la API en JSON. | `ghub sync SRP045416 --json` |

### `ghub search`

Consulta metadatos locales. Intenta sincronizar automáticamente si el ID falta.

**Sintaxis:**

```bash
ghub search [IDS...] [OPCIONES]

```

**Argumentos:**

* **`[IDS...]`**: Uno o varios identificadores válidos de NCBI separados por espacios.

**Opciones:**

| Opción | Descripción | Ejemplo de uso con bandera |
| --- | --- | --- |
| `--page INTEGER` | Número de página para resultados paginados (defecto: 1). | `ghub search PRJNA257197 --page 2` |
| `--page-size INT` | Elementos por página (defecto: 20). | `ghub search SRP045416 --page-size 50` |
| `--json` | Salida en JSON crudo. | `ghub search SRR1972976 --json` |

### `ghub explore`

Busca BioProjects en NCBI por texto libre.

**Sintaxis:**

```bash
ghub explore "QUERY" [OPCIONES]

```

**Argumentos:**

* **`"QUERY"`**: Cadena de búsqueda para NCBI entre comillas.

**Opciones:**

| Opción | Descripción | Ejemplo de uso con bandera |
| --- | --- | --- |
| `--page INTEGER` | Número de página (defecto: 1). | `ghub explore "ebola siera leone" --page 3` |
| `--page-size INT` | Elementos por página (defecto: 20). | `ghub explore "transcriptome human" --page-size 10` |
| `-i, --ids` | Muestra únicamente los IDs de los BioProjects encontrados (útil para scripts). | `ghub explore "Zaire ebolavirus" --ids` |
| `--json` | Salida en JSON crudo. | `ghub explore "PRJNA257197" --json` |

---

### `ghub export`

El comando `export` extrae y formatea el árbol completo de metadatos asociado a uno o múltiples identificadores. Se encarga de verificar, sincronizar (si es necesario) y empaquetar los datos en estructuras óptimas para el análisis bioinformático.

#### Sintaxis

```bash
ghub export [IDS...] [OPCIONES]

```

#### Argumentos

* **`[IDS...]`**: Uno o varios identificadores válidos de NCBI separados por espacios (ej. `PRJNA257197`, `SRS908478`). El sistema rastreará toda la rama jerárquica relacionada.

#### Opciones

| Opción | Alias | Descripción |
| --- | --- | --- |
| `--format` |  | Define el formato de salida. Valores permitidos: `csv` (por defecto) o `json`. |
| `--flat` | `-f` | *(Solo para CSV)*. Aplana toda la jerarquía relacional en una única tabla horizontal, ideal para análisis directo en Excel, Python (Pandas) o R. |
| `--strict` | `-s` | Omite registros "huérfanos". Si una Muestra o Experimento no tiene archivos físicos finales asociados (*Runs*), no se incluirá en la exportación. |
| `--out` | `-o` | Define la ruta y el nombre del archivo resultante. Si se omite, se genera automáticamente. |

**Ejemplos de uso con banderas:**

* `ghub export PRJNA257197 --flat --strict` (exportación CSV aplanada, omitiendo registros sin Runs).
* `ghub export SRR1972976 --format json -o run_data.json` (exportación JSON cruda a archivo específico).

**Modos de Exportación y Estructura**

1. **Modo Estándar (ZIP Relacional)**
Comando: `ghub export PRJNA257197`
Genera un archivo `.zip` que contiene cuatro archivos CSV normalizados y relacionados entre sí mediante llaves foráneas (`bioproject_accession`, `sample_accession`, etc.):
* `bioprojects.csv`
* `samples.csv`
* `experiments.csv`
* `runs.csv`: Incluye la columna `size_bytes` con el tamaño crudo para cálculos numéricos.


2. **Modo Aplanado (El "Data Mart")**
Comando: `ghub export PRJNA257197 --flat`
Combina las cuatro tablas en un solo archivo CSV expansivo.
* **Estructura Visual:** Congela el mapa de identificadores a la izquierda (Macro ➔ Micro) y despliega los detalles descriptivos hacia la derecha.
* **Atributos Dinámicos:** Los atributos biológicos de las muestras (Sample Attributes) se "explotan" automáticamente en columnas independientes y filtrables con el prefijo `attr_` (ej. `attr_host`, `attr_tissue`, `attr_collection_date`), eliminando los bloques de texto aglomerados.


3. **Modo Desarrollador (JSON Crudo)**
Comando: `ghub export PRJNA257197 --format json`
Vuelca la estructura de árbol jerárquico cruda retornada por la API. Ideal para scripts o migración de datos.

---

### `ghub download`

Descarga archivos de secuencia (Runs). Requiere un flujo de autenticación de contraseña de un solo uso (OTP).

**Sintaxis:**

```bash
ghub download RUN_ID [OPCIONES]

```

**Argumentos:**

* **`RUN_ID`**: Identificador válido de Run de NCBI (ej. `SRR1972976`).

**Opciones:**

| Opción | Alias | Descripción |
| --- | --- | --- |
| `--email TEXT` |  | Correo institucional a usar para la descarga (sobrescribe temporalmente el correo guardado en la configuración). |
| `--output TEXT` | `-o` | Ruta de destino (directorio o archivo específico .tar.gz). |
| `--wait` | `-w` | Bloquea la terminal y muestra progreso en tiempo real hasta que el servidor termine de preparar el archivo y la descarga finalice automáticamente. |

**Flujo:**
Solicita el código OTP si es necesario. Sin `-w`, encola la tarea de preparación y finaliza. Con `-w`, espera a que finalice la preparación y procede a descargar el archivo automáticamente.

**Ejemplos de uso con banderas:**

* `ghub download SRR1972976 --email usuario@unam.mx` (usa este correo temporalmente).
* `ghub download SRR1972976 -o ./mis_secuencias/` (personaliza la salida).
* `ghub download SRR1972976 -w` (bloquea la terminal hasta descargar).

---

Tienes toda la razón. Ese límite de 120 IDs es una restricción general del backend para cualquier operación masiva (*bulk*) para garantizar la estabilidad del servidor.

Aquí tienes la sección **Notas de Uso** del README actualizada para reflejar que este límite aplica a todos los comandos que aceptan múltiples IDs (como `check`, `sync`, `search` y `export`):

---

## Notas de Uso

* **Límite de Operaciones Masivas (Bulk):** Existe un límite máximo de **120 IDs** por solicitud en cualquier comando que acepte múltiples identificadores (ej. `check`, `sync`, `search`, `export`). Si necesitas procesar más de 120 IDs, deberás dividir la lista y ejecutar el comando varias veces.
* **Aplanado (`--flat`):** Ideal para análisis en Excel. Esta opción crea columnas filtrables independientes con el prefijo `attr_` para cada atributo biológico de la muestra, facilitando la organización de datos dispersos.
* **Valores `missing`:** Es un estándar oficial de NCBI que indica que el investigador original no proporcionó ese dato específico para la muestra. No implica un error en la base de datos de Genomic Hub ni en la CLI.
```