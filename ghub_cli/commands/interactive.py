import sys
import math
import time
import click

from ghub_cli.core.config import load_config, save_config
from ghub_cli.core.client import APIError
from ghub_cli.utils.formatters import print_api_error
from ghub_cli.utils.tasks import poll_task, FAILURE_STATES
from ghub_cli.utils.email import CONTACT_EMAIL, guardar_email, validar_y_guardar_email
from ghub_cli.commands.search import search


def main_menu(ctx):
    """Menú interactivo de bienvenida."""
    click.clear()
    click.secho("╔══════════════════════════════════════════════════╗", fg="cyan", bold=True)
    click.secho("║         Bienvenido a Genomic Hub CLI             ║", fg="cyan", bold=True)
    click.secho("║  Plataforma de acceso a datos genómicos del ICAT ║", fg="cyan", bold=True)
    click.secho("╚══════════════════════════════════════════════════╝", fg="cyan", bold=True)
    click.echo("\n  [1]  Consulta    — busca y explora proyectos genómicos")
    click.echo("  [2]  Descarga    — descarga secuencias SRR")
    click.echo("  [0]  Salir\n")

    opcion = click.prompt("Selecciona una opción", type=click.Choice(["0", "1", "2"]), show_choices=False)

    if opcion == "0":
        click.echo("¡Hasta luego!")
        sys.exit(0)
    elif opcion == "1":
        _menu_consulta(ctx)
    elif opcion == "2":
        _flujo_descarga(ctx)


# =========================================
# Paginación (compartida entre búsquedas)
# =========================================
def _prompt_page_number(total_pages: int) -> int:
    """Pide un número de página, reintentando con un mensaje propio si está fuera de rango."""
    while True:
        raw = click.prompt("  Número de página", type=int)
        if 1 <= raw <= total_pages:
            return raw
        click.secho(
            f"  Error: no hay {raw} páginas para este proyecto, "
            f"coloca un número dentro de este rango (1-{total_pages}).",
            fg="red",
        )


def _prompt_pagination_action(page: int, total_pages: int) -> str:
    """Muestra el submenú de navegación y devuelve la acción elegida."""
    click.echo(f"\n  ── Página {page} de {total_pages} ──")
    labels, choices = [], []
    if page < total_pages:
        labels.append("[n] Siguiente página")
        choices.append("n")
    if page > 1:
        labels.append("[p] Página anterior")
        choices.append("p")
    labels.append("[g] Ir a página")
    choices.append("g")
    labels.append("[0] Volver al menú de consulta")
    choices.append("0")
    click.echo("  " + "   ".join(labels))

    action = click.prompt("  Selecciona una opción", type=click.Choice(choices), show_choices=False)
    if action == "g":
        return f"g:{_prompt_page_number(total_pages)}"
    return action


def _explore_menu(client, query: str, page_size: int = 20):
    """Busca por texto libre en NCBI, con navegación de páginas."""
    page = 1
    while True:
        try:
            result = client.explore(query, page=page, page_size=page_size)
        except APIError as e:
            print_api_error(e)
            return

        total_items = result.get("total_items", result.get("total", 0))
        total_pages = math.ceil(total_items / page_size) if page_size else 1

        click.echo(f"\n  Total: {total_items} resultados (página {page} de {total_pages})\n")
        for r in result.get("data", result.get("results", [])):
            click.echo(f"  {r.get('bioproject_accession', '-'):<15} {r.get('organism') or '-':<25} {r.get('title') or ''}")

        if total_pages <= 1:
            return

        action = _prompt_pagination_action(page, total_pages)
        if action == "0":
            return
        elif action == "n":
            page += 1
        elif action == "p":
            page -= 1
        elif action.startswith("g:"):
            page = int(action.split(":", 1)[1])


def _search_id_menu(ctx, target_id: str, page_size: int = 20):
    """Consulta un ID en Genomic-Hub, con navegación de páginas."""
    page = 1
    while True:
        click.echo()
        try:
            final_data = ctx.invoke(search, raw_ids=(target_id,), page=page, page_size=page_size)
        except SystemExit:
            return

        pagination = next(
            (item.get("pagination") for item in (final_data or []) if item.get("pagination")),
            None,
        )
        if not pagination:
            return

        total_items = pagination.get("total_items", 0)
        total_pages = math.ceil(total_items / page_size) if page_size else 1
        if total_pages <= 1:
            return

        action = _prompt_pagination_action(page, total_pages)
        if action == "0":
            return
        elif action == "n":
            page += 1
        elif action == "p":
            page -= 1
        elif action.startswith("g:"):
            page = int(action.split(":", 1)[1])


# =========================================
# Menú de consulta
# =========================================
def _menu_consulta(ctx):
    click.echo("\n── Consulta ─────────────────────────────────────────")
    click.echo("\n  [1]  Buscar en NCBI por texto libre")
    click.echo("  [2]  Ver datos locales de un ID (con auto-sincronización)")
    click.echo("  [3]  Verificar si un ID existe localmente")
    click.echo("  [0]  Volver al menú principal\n")

    opcion = click.prompt("Selecciona una opción", type=click.Choice(["0", "1", "2", "3"]), show_choices=False)
    client = ctx.obj["client"]

    if opcion == "0":
        main_menu(ctx)
        return
    elif opcion == "1":
        query = click.prompt("Término de búsqueda")
        _explore_menu(client, query)
    elif opcion == "2":
        target_id = click.prompt("ID a consultar")
        _search_id_menu(ctx, target_id)
    elif opcion == "3":
        target_id = click.prompt("ID a verificar")
        try:
            result = client.check_bulk([target_id])
            exists = target_id in result.get("existing_ids", [])
            color = "green" if exists else "yellow"
            click.secho(f"\n  {target_id}: {'✓ existe' if exists else '✗ no existe'}", fg=color)
        except APIError as e:
            print_api_error(e)

    click.echo()
    _menu_consulta(ctx)


def _tras_error(ctx, mensaje_reintento: str = "¿Quieres intentarlo de nuevo?"):
    """
    Punto de salida único para cualquier error dentro del flujo de descarga.
    Nunca deja que el proceso simplemente termine: o reintenta la descarga
    desde el inicio, o regresa al menú principal, o sale explícitamente
    si el usuario lo pide.
    """
    click.echo()
    if click.confirm(mensaje_reintento, default=True):
        _flujo_descarga(ctx)
        return
    if click.confirm("¿Volver al menú principal?", default=True):
        main_menu(ctx)
        return
    click.echo("¡Hasta luego!")
    sys.exit(0)


def _poll_file_status(client, run_id: str, interval: float = 3.0, timeout: float = 300.0) -> str:
    """
    Consulta /download/file-status/{run_id} repetidamente hasta que el archivo
    quede en un estado terminal (COMPLETED/FAILED) o se agote el timeout.
    """
    elapsed = 0.0
    while elapsed < timeout:
        try:
            result = client.file_status(run_id)
        except APIError as e:
            print_api_error(e)
            return "FAILED"

        status = result.get("status")
        if status in ("COMPLETED", "FAILED"):
            return status

        time.sleep(interval)
        elapsed += interval

    return "TIMEOUT"


def _flujo_descarga(ctx):
    client = ctx.obj["client"]
    cfg = load_config()

    click.echo("\n── Descarga de secuencias ───────────────────────────\n")

    # --- Paso 1: credenciales ---
    email = cfg.get("email")
    if email:
        click.echo(f"  Email registrado: {click.style(email, fg='green')}")
        if not click.confirm("  ¿Usar este email?", default=True):
            email = None

    if not email:
        email = click.prompt("  Ingresa tu correo institucional")
        if not validar_y_guardar_email(client, cfg, email):
            _tras_error(ctx, "¿Intentar con otro correo?")
            return

    # --- Paso 2: pedir el SRR ---
    run_id = click.prompt("\n  Ingresa el ID de la secuencia a descargar (ej. SRR1972976)")

    # --- Paso 3: solicitar OTP ---
    click.echo("\n  Solicitando código de verificación...")
    try:
        req = client.request_download(run_id, email)
        request_id = req.get("request_id")
    except APIError as e:
        if e.status_code == 400 and "denegado" in e.detail.lower():
            click.secho("  ✗ Este correo no tiene autorización.", fg="red")
            click.secho(f"  Si crees que debería tener acceso, escribe a: {CONTACT_EMAIL}", fg="yellow")
            cfg.pop("email", None)
            save_config(cfg)
            _tras_error(ctx, "¿Intentar con otro correo?")
        elif e.status_code == 404:
            click.secho(f"  ✗ El run '{run_id}' no existe en la base de datos local.", fg="red")
            click.secho(f"  Prueba sincronizarlo primero, ej: ghub search {run_id}", fg="yellow")
            _tras_error(ctx, "¿Intentar con otro ID?")
        else:
            print_api_error(e)
            _tras_error(ctx)
        return

    # --- Caso especial: archivo ya listo y autorizado (request_id=None) ---
    if request_id is None:
        click.secho("  ✓ El archivo ya está disponible para tu correo.", fg="green")
        _descargar_archivo(ctx, client, run_id, email)
        return

    # --- Paso 4: OTP normal ---
    click.secho("  ✓ Código enviado a tu correo.", fg="green")
    otp_code = click.prompt("\n  Código de verificación recibido")
    click.echo("\n  Verificando código...")
    try:
        verify_result = client.verify_otp(request_id, email, otp_code)
        click.secho("  ✓ Código verificado. Iniciando preparación...", fg="green")
    except APIError as e:
        print_api_error(e)
        _tras_error(ctx)
        return

    # --- Paso 5: esperar a que el archivo esté listo ---
    task_id = verify_result.get("task_id")

    if task_id == "ALREADY_CONFIRMED":
        click.secho("  ✓ El archivo ya estaba listo.", fg="green")

    elif task_id == "LINKED_TO_EXISTING_DOWNLOAD":
        click.secho("  ⧗ Otra persona ya está preparando este archivo. Esperando...", fg="yellow")
        final_status = _poll_file_status(client, run_id)
        if final_status == "FAILED":
            click.secho("  ✗ La preparación del archivo falló.", fg="red")
            _tras_error(ctx)
            return
        elif final_status != "COMPLETED":
            click.secho(
                "\n  El archivo sigue preparándose. Vuelve a intentar en unos minutos.", fg="yellow"
            )
            if click.confirm("\n  ¿Volver al menú principal?", default=True):
                main_menu(ctx)
            return

    elif task_id:
        # task_id real de Celery: esta petición SÍ inició la preparación
        final = poll_task(client, task_id, interval=3.0, label="Preparando archivo", show_result=False)
        if final is None:
            click.secho("\n  La descarga sigue preparándose. Retómala con:", fg="yellow")
            click.secho(f"    ghub task {task_id} --poll", fg="yellow", bold=True)
            if click.confirm("\n  ¿Volver al menú principal?", default=True):
                main_menu(ctx)
            return
        if final.get("status") in FAILURE_STATES:
            click.secho("  ✗ La preparación del archivo falló.", fg="red")
            _tras_error(ctx)
            return

    # --- Paso 6: descarga ---
    _descargar_archivo(ctx, client, run_id, email)


def _descargar_archivo(ctx, client, run_id: str, email: str):
    """Pide ruta de destino y descarga el archivo."""
    output = click.prompt(
        "\n  Ruta de destino (Enter para directorio actual)",
        default="", show_default=False
    ).strip() or None

    click.echo("  Descargando...")
    try:
        saved_path = client.download_file(run_id, email, output_path=output)
        click.secho(f"\n  ✓ Archivo guardado en: {saved_path}", fg="green", bold=True)
    except APIError as e:
        print_api_error(e)
        _tras_error(ctx)
        return

    if click.confirm("\n  ¿Volver al menú principal?", default=True):
        main_menu(ctx)