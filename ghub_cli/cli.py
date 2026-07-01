"""
Genomic Hub CLI
================
Cliente de línea de comandos para interactuar con la API de genomic-hub.
"""
import sys

import click

from .client import GenomicHubClient, APIError
from .config import load_config, save_config, DEFAULT_BASE_URL
from .utils import poll_task, pretty_json, print_api_error, FAILURE_STATES

MAX_BULK_IDS = 120
CONTACT_EMAIL = "leticiavega@icar.unam.mx"


def get_client(ctx) -> GenomicHubClient:
    return ctx.obj["client"]


# =========================================
# GRUPO RAÍZ — menú interactivo de bienvenida
# =========================================
@click.group(invoke_without_command=True)
@click.option(
    "--base-url",
    default=None,
    help=f"URL base de la API (default: {DEFAULT_BASE_URL}).",
)
@click.option("--timeout", default=30, show_default=True, help="Timeout de red en segundos.")
@click.pass_context
def cli(ctx, base_url, timeout):
    """Genomic Hub CLI — sincroniza, consulta y descarga secuencias genómicas."""
    cfg = load_config()
    url = base_url or cfg.get("base_url", DEFAULT_BASE_URL)
    ctx.ensure_object(dict)
    ctx.obj["client"] = GenomicHubClient(base_url=url, timeout=timeout)

    # Si se invocó un subcomando directamente (ej. `ghub sync ...`), no mostramos el menú
    if ctx.invoked_subcommand is not None:
        return

    _menu_principal(ctx)


def _menu_principal(ctx):
    """Menú interactivo de bienvenida."""
    click.clear()
    click.secho("╔══════════════════════════════════════════════════╗", fg="cyan", bold=True)
    click.secho("║         Bienvenido a Genomic Hub CLI             ║", fg="cyan", bold=True)
    click.secho("║  Plataforma de acceso a datos genómicos del ICAT ║", fg="cyan", bold=True)
    click.secho("╚══════════════════════════════════════════════════╝", fg="cyan", bold=True)
    click.echo()
    click.echo("  [1]  Consulta    — busca y explora proyectos genómicos")
    click.echo("  [2]  Descarga    — descarga secuencias SRR")
    click.echo("  [0]  Salir")
    click.echo()

    opcion = click.prompt("Selecciona una opción", type=click.Choice(["0", "1", "2"]), show_choices=False)

    if opcion == "0":
        click.echo("¡Hasta luego!")
        sys.exit(0)
    elif opcion == "1":
        _menu_consulta(ctx)
    elif opcion == "2":
        _flujo_descarga(ctx)


# =========================================
# MENÚ CONSULTA
# =========================================
def _menu_consulta(ctx):
    click.echo()
    click.secho("── Consulta ─────────────────────────────────────────", fg="cyan")
    click.echo()
    click.echo("  [1]  Buscar en NCBI por texto libre")
    click.echo("  [2]  Ver datos locales de un ID")
    click.echo("  [3]  Verificar si un ID existe localmente")
    click.echo("  [0]  Volver al menú principal")
    click.echo()

    opcion = click.prompt("Selecciona una opción", type=click.Choice(["0", "1", "2", "3"]), show_choices=False)
    client = get_client(ctx)

    if opcion == "0":
        _menu_principal(ctx)
    elif opcion == "1":
        query = click.prompt("Término de búsqueda")
        try:
            result = client.explore(query, page=1, page_size=20)
            click.echo()
            click.echo(f"  Total: {result['total']} resultados\n")
            for r in result["results"]:
                click.echo(f"  {r['bioproject_accession']:<15} {r.get('organism') or '-':<25} {r.get('title') or ''}")
        except APIError as e:
            print_api_error(e)
    elif opcion == "2":
        target_id = click.prompt("ID a consultar (BioProject, SRR, etc.)")
        try:
            result = client.search(target_id)
            click.echo()
            click.echo(pretty_json(result["data"]))
        except APIError as e:
            print_api_error(e)
    elif opcion == "3":
        target_id = click.prompt("ID a verificar")
        try:
            result = client.check(target_id)
            exists = result["exists_locally"]
            color = "green" if exists else "yellow"
            click.secho(
                f"\n  {target_id}: {'✓ existe localmente' if exists else '✗ no existe localmente'}",
                fg=color,
            )
        except APIError as e:
            print_api_error(e)

    click.echo()
    if click.confirm("¿Volver al menú principal?", default=True):
        _menu_principal(ctx)


# =========================================
# FLUJO DESCARGA
# =========================================
def _flujo_descarga(ctx):
    client = get_client(ctx)
    cfg = load_config()

    click.echo()
    click.secho("── Descarga de secuencias ───────────────────────────", fg="cyan")
    click.echo()

    # --- Paso 1: credenciales (solo se piden si no están guardadas) ---
    email = cfg.get("email")
    if email:
        click.echo(f"  Email registrado: {click.style(email, fg='green')}")
        if not click.confirm("  ¿Usar este email?", default=True):
            email = None

    if not email:
        email = click.prompt("  Ingresa tu correo institucional")

        # Validar contra la BD antes de continuar
        click.echo("  Verificando acceso...")
        try:
            # Hacemos una llamada de prueba con un run_id dummy para comprobar el email.
            # Si el error es NOT_FOUND (run no existe) el email sí está autorizado.
            # Si el error es BAD_REQUEST/Acceso denegado, el email no está registrado.
            client.request_download("__check__", email)
            # Si llega aquí (200) también está ok — raro con __check__ pero lo manejamos
            _guardar_email(cfg, email)
        except APIError as e:
            if e.status_code == 400 and "denegado" in e.detail.lower():
                click.echo()
                click.secho("  ✗ Este correo no está registrado.", fg="red", bold=True)
                click.secho(
                    f"  Para solicitar acceso escribe a: {CONTACT_EMAIL}",
                    fg="yellow",
                )
                click.echo()
                if click.confirm("  ¿Intentar con otro correo?", default=True):
                    _flujo_descarga(ctx)
                return
            elif e.status_code == 404 or "no existe" in e.detail.lower():
                # El run __check__ no existe pero el email sí pasó la validación
                _guardar_email(cfg, email)
            else:
                # Error de red u otro inesperado
                print_api_error(e)
                return

    # --- Paso 2: pedir el SRR ---
    click.echo()
    run_id = click.prompt("  Ingresa el ID de la secuencia a descargar (ej. SRR1972976)")

    # --- Paso 3: solicitar OTP ---
    click.echo()
    click.echo("  Solicitando código de verificación...")
    try:
        client.request_download(run_id, email)
        click.secho("  ✓ Código enviado a tu correo.", fg="green")
    except APIError as e:
        if e.status_code == 400 and "denegado" in e.detail.lower():
            # El email guardado fue revocado desde que se guardó
            click.secho("  ✗ Tu correo ya no tiene acceso autorizado.", fg="red")
            click.secho(f"  Contacta a: {CONTACT_EMAIL}", fg="yellow")
            cfg.pop("email", None)
            save_config(cfg)
        else:
            print_api_error(e)
        return

    # --- Paso 4: verificar OTP ---
    click.echo()
    otp_code = click.prompt("  Código de verificación recibido")
    click.echo()
    click.echo("  Verificando código...")
    try:
        verify_result = client.verify_otp(run_id, email, otp_code)
        click.secho("  ✓ Código verificado. Iniciando preparación del archivo...", fg="green")
    except APIError as e:
        print_api_error(e)
        return

    # --- Paso 5: esperar que la tarea Celery termine ---
    click.echo()
    task_id = verify_result.get("task_id")
    if task_id and task_id not in ("ALREADY_CONFIRMED", "LINKED_TO_EXISTING_DOWNLOAD"):
        # Las descargas (prefetch + fasterq-dump + compresión) pueden tardar
        # hasta ~30 min. Un timeout aquí NO significa que la tarea falló -
        # sigue corriendo en el servidor; solo dejamos de esperar en este
        # comando y avisamos cómo retomarla.
        final = poll_task(
            client,
            task_id,
            interval=3.0,
            max_wait=1800,
            label="Preparando archivo",
            show_result=False,
        )
        if final is None:
            click.secho(
                "  La descarga sigue preparándose en el servidor. Retómala con:",
                fg="yellow",
            )
            click.secho(f"    ghub task {task_id} --poll", fg="yellow", bold=True)
            return
        if final.get("status") in FAILURE_STATES:
            click.secho("  ✗ La preparación del archivo falló.", fg="red")
            if final.get("detail"):
                click.secho(f"  detail: {final['detail']}", fg="red", dim=True)
            return
    else:
        click.secho("  ✓ El archivo ya estaba listo.", fg="green")

    # --- Paso 6: confirmar descarga y ruta ---
    click.echo()
    click.secho("  ✓ Archivo listo para descargar.", fg="green")
    output = click.prompt(
        "  Ruta de destino (Enter para usar el directorio actual)",
        default="",
        show_default=False,
    )
    output = output.strip() or None

    click.echo("  Descargando...")
    try:
        saved_path = client.download_file(run_id, email, output_path=output)
        click.echo()
        click.secho(f"  ✓ Archivo guardado en: {saved_path}", fg="green", bold=True)
    except APIError as e:
        print_api_error(e)
        return

    click.echo()
    if click.confirm("  ¿Volver al menú principal?", default=True):
        _menu_principal(ctx)


def _guardar_email(cfg: dict, email: str):
    cfg["email"] = email
    save_config(cfg)
    click.secho(f"  ✓ Correo guardado para futuras sesiones.", fg="green")


# =========================================
# SUBCOMANDOS DIRECTOS (para scripting/CLI avanzado)
# =========================================
@cli.group()
def config():
    """Configuración persistente del CLI."""


@config.command("set-url")
@click.argument("url")
def config_set_url(url):
    """Guarda la URL base de la API."""
    cfg = load_config()
    cfg["base_url"] = url.rstrip("/")
    save_config(cfg)
    click.echo(f"URL base guardada: {cfg['base_url']}")


@config.command("show")
def config_show():
    """Muestra la configuración actual."""
    cfg = load_config()
    click.echo(f"base_url : {cfg.get('base_url', DEFAULT_BASE_URL)}")
    click.echo(f"email    : {cfg.get('email', '(no guardado)')}")


@cli.command("sync")
@click.argument("project_id")
@click.pass_context
def sync_single(ctx, project_id):
    """Sincroniza un solo PROJECT_ID (ej. PRJNA12345)."""
    client = get_client(ctx)
    try:
        result = client.sync(project_id)
        click.secho(f"✓ Sync encolado. task_id={result['task_id']}", fg="green")
        poll_task(client, result["task_id"])
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@cli.command("sync-bulk")
@click.argument("project_ids", nargs=-1, required=True)
@click.option("--from-file", type=click.Path(exists=True, dir_okay=False))
@click.option("--poll/--no-poll", default=True)
@click.pass_context
def sync_bulk(ctx, project_ids, from_file, poll):
    """Sincroniza varios PROJECT_IDS (máximo 120)."""
    client = get_client(ctx)
    ids = list(project_ids)
    if from_file:
        with open(from_file) as f:
            ids.extend(line.strip() for line in f if line.strip())
    seen = set()
    ids = [x for x in ids if not (x in seen or seen.add(x))]
    if not ids:
        click.secho("No se proporcionó ningún project_id.", fg="red")
        sys.exit(1)
    if len(ids) > MAX_BULK_IDS:
        click.secho(f"✗ Máximo {MAX_BULK_IDS} IDs por solicitud (recibidos: {len(ids)}).", fg="red")
        sys.exit(1)
    click.echo(f"Sincronizando {len(ids)} proyecto(s)...")
    try:
        result = client.sync_bulk(ids)
        click.secho(f"✓ Sync-bulk encolado. task_id={result['task_id']}", fg="green")
        if poll:
            poll_task(client, result["task_id"])
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@cli.command("check")
@click.argument("target_id")
@click.pass_context
def check(ctx, target_id):
    """Verifica si TARGET_ID existe en la base local."""
    client = get_client(ctx)
    try:
        result = client.check(target_id)
        exists = result["exists_locally"]
        click.secho(
            f"{target_id}: {'✓ existe localmente' if exists else '✗ no existe localmente'}",
            fg="green" if exists else "yellow",
        )
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@cli.command("search")
@click.argument("target_id")
@click.pass_context
def search(ctx, target_id):
    """Obtiene datos locales de TARGET_ID."""
    client = get_client(ctx)
    try:
        result = client.search(target_id)
        click.echo(pretty_json(result["data"]))
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@cli.command("explore")
@click.argument("query")
@click.option("--page", default=1, show_default=True)
@click.option("--page-size", default=20, show_default=True)
@click.pass_context
def explore(ctx, query, page, page_size):
    """Busca BioProjects en NCBI por texto libre."""
    client = get_client(ctx)
    try:
        result = client.explore(query, page, page_size)
        click.echo(f"Total: {result['total']} resultados (página {result['page']})\n")
        for r in result["results"]:
            click.echo(f"  {r['bioproject_accession']:<15} {r.get('organism') or '-':<25} {r.get('title') or ''}")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@cli.command("download")
@click.argument("run_id")
@click.option("--email", required=True, help="Correo institucional ya registrado.")
@click.option("-o", "--output", default=None, help="Ruta de destino del archivo.")
@click.pass_context
def download(ctx, run_id, email, output):
    """
    Descarga RUN_ID para --email, sin pasar por el menú interactivo.

    Si ya tienes una autorización CONFIRMADA para este run_id + email (por
    ejemplo porque ya pasaste el flujo de OTP antes, o el CLI se quedó
    esperando y la tarea terminó del lado del servidor — como cuando te
    llega el correo de "descarga completada"), este comando descarga el
    archivo directo, sin pedir OTP de nuevo.

    Si es la primera vez que este email pide este archivo, sí hace falta
    el flujo completo con OTP — usa el menú interactivo (`ghub`, opción 2)
    para eso.
    """
    client = get_client(ctx)

    # Intento directo: si ya hay autorización confirmada y el archivo está
    # listo, esto basta y no hace falta tocar /download/request ni OTP.
    click.echo("  Verificando si el archivo ya está disponible para este correo...")
    try:
        saved_path = client.download_file(run_id, email, output_path=output)
        click.secho(f"✓ Archivo guardado en: {saved_path}", fg="green", bold=True)
        return
    except APIError as e:
        print_api_error(e)
        if e.status_code == 404 or (e.status_code == 400 and "autorizaci" in e.detail.lower()):
            click.secho(
                "\n  Si ya hiciste el flujo de OTP para este run_id y solo se agotó el\n"
                "  tiempo de espera, corre: ghub task <task_id> --poll\n"
                "  (el task_id se mostró al verificar el OTP). Cuando termine, vuelve\n"
                "  a correr este comando.\n"
                "  Si nunca has pedido este archivo con este correo, usa el menú\n"
                "  interactivo (`ghub`, opción 2) para completar el flujo de OTP.",
                fg="yellow",
            )
        sys.exit(1)


@cli.command("task")
@click.argument("task_id")
@click.option("--poll/--no-poll", default=False)
@click.pass_context
def task_status(ctx, task_id, poll):
    """Consulta el estado de una tarea asíncrona."""
    client = get_client(ctx)
    try:
        if poll:
            poll_task(client, task_id)
        else:
            result = client.task_status(task_id)
            click.echo(pretty_json(result))
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


# =========================================
# Helpers
# =========================================
# pretty_json, print_api_error y poll_task viven en utils.py

if __name__ == "__main__":
    cli()