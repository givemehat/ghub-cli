# ghub-cli

CLI de línea de comandos para `genomic-hub`: sincronización masiva de
proyectos, búsqueda de metadatos y descarga de secuencias con flujo OTP.
Pensado para staff/admins que necesitan operar lotes grandes sin pasar por
el frontend (límite de 120 IDs por sync, vs. 12 que aplica el front).

## Estructura

```
genomic-hub-cli/
├── README.md
├── pyproject.toml        # empaquetado, registra el comando `ghub`
└── ghub_cli/
    ├── __init__.py
    ├── cli.py             # comandos de Click (sync, download, check, etc.)
    ├── client.py          # wrapper HTTP sobre la API (rutas + manejo de errores)
    ├── config.py          # persistencia de --base-url en ~/.config/ghub-cli/
    └── utils/
        ├── email.py       # resolución/validación/guardado del correo de descarga
        └── tasks.py       # polling de tareas Celery + spinner de progreso
```

## Instalación

```bash
cd genomic-hub-cli
pip install -e .
```

Esto instala el comando `ghub` en tu PATH.

## Configuración

Por defecto apunta a `http://127.0.0.1:8000`. Para cambiarlo de forma
persistente:

```bash
ghub config set-url http://tu-servidor:8000
ghub config show
```

O pásalo al vuelo en cualquier comando con `--base-url`:

```bash
ghub --base-url http://tu-servidor:8000 check SRR1972976
```

### Correo institucional

Para no tener que pasar `--email` en cada descarga (o pasar por el menú
interactivo la primera vez), puedes guardarlo y validarlo directamente:

```bash
ghub config set-email tu@correo.com    # lo valida contra la API y lo guarda
ghub config unset-email                # lo olvida
ghub config show                       # ver qué correo/URL están guardados
```

Una vez guardado, `ghub download <run_id>` lo usa automáticamente sin
necesidad de la bandera `--email` (ver sección "Descarga" más abajo).

## Comandos

### Sincronización

```bash
# Un solo proyecto
ghub sync PRJNA12345

# Varios proyectos (máximo 120, validado localmente antes de pegarle al backend)
ghub sync-bulk PRJNA1 PRJNA2 PRJNA3

# Desde un archivo de texto (un ID por línea)
ghub sync-bulk --from-file ids.txt

# Combinando archivo + args sueltos
ghub sync-bulk PRJNA999 --from-file ids.txt
```

Por defecto, `sync` y `sync-bulk` hacen polling del `task_id` resultante y
muestran el resultado final. Usa `--no-poll` para solo encolar y salir.

### Búsqueda y consulta

```bash
ghub check SRR1972976              # ¿existe localmente?
ghub search SRR1972976             # árbol de datos local
ghub explore "human genome" --page 1 --page-size 10   # busca en NCBI
ghub task <task_id>                # estado de una tarea
ghub task <task_id> --poll         # espera hasta que termine
```

### Descarga (flujo OTP completo)

```bash
# usa el correo guardado; si no hay ninguno, lo pide y lo guarda
ghub download SRR1972976

# usa este correo solo para esta corrida, sin sobrescribir el guardado
ghub download SRR1972976 --email tu@correo.com

# ruta de destino personalizada
ghub download SRR1972976 -o ./data/SRR1972976.tar.gz
```

`--email` es opcional:

- Si lo pasas, se usa ese correo **solo para esta ejecución** — nunca
  sobrescribe el que ya tengas guardado.
- Si lo omites, se usa el correo guardado en
  `~/.config/ghub-cli/config.json`.
- Si no hay ninguno guardado, el CLI te lo pide, lo valida contra la API
  y lo guarda para futuras sesiones (mismo comportamiento que el menú
  interactivo).

Esto hace todo el flujo en un solo comando:
1. Resuelve el correo a usar (guardado / `--email` / lo pide y lo guarda)
2. Solicita la descarga (`/download/request`)
3. Si ese `run_id` nunca se había verificado con ese correo, te pide el
   código OTP que llega por email (esta parte no se puede automatizar:
   el código solo lo tienes tú, en tu correo). Si ya lo habías verificado
   antes para ese mismo `run_id` + correo, se lo salta.
4. Verifica el OTP (`/download/verify`)
5. Espera a que el archivo esté listo (usa `--no-poll` para solo encolar
   la preparación y salir, sin bloquear la terminal — luego retómalo con
   `ghub task <task_id> --poll`)
6. Descarga el archivo al directorio actual (o a `-o/--output` si lo das)

> **Nota:** como el código OTP llega por correo, el comando sí se queda
> esperando tu input (`click.prompt`) cuando el run es nuevo — no es
> apto para correrlo desde un cron/script sin nadie enfrente. Si
> necesitas eso, lo resolvemos separando `request`/`verify` en dos
> subcomandos independientes.

### Administración

```bash
ghub register-email --admin-id 1 --name "Juan Pérez" --email juan@ejemplo.com
```

## Notas de seguridad

- El límite de 120 IDs en `sync-bulk` se valida **antes** de llamar al
  backend (evita requests innecesarios), pero el backend debe seguir
  validándolo también — el CLI es una capa de UX, no el control de
  seguridad real.
- `download` requiere pasar por el flujo OTP completo; no hay atajo para
  descargar sin haber verificado el código.
- El correo se guarda en texto plano en `~/.config/ghub-cli/config.json`
  tras ser validado contra la API. Pasar `--email` en un comando puntual
  nunca sobrescribe ese valor guardado.