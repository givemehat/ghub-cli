"""
Genomic Hub CLI
================
Cliente de línea de comandos para interactuar con la API de genomic-hub:
sincronización masiva de proyectos, búsqueda/check de IDs y descarga de
secuencias con flujo OTP.

Pensado para uso de staff/admins que necesitan sincronizar lotes grandes
(hasta 120 IDs, el límite que aplica el backend solo para este canal).
"""
import sys

import click

from .client import GenomicHubClient, APIError
from .config import load_config, save_config, DEFAULT_BASE_URL
from .utils import poll_task, pretty_json, print_api_error

MAX_BULK_IDS = 120


def get_client(ctx) -> GenomicHubClient:
    return ctx.obj["client"]


@click.group()
@click.option(
    "--base-url",
    default=None,
    help=f"URL base de la API (default: {DEFAULT_BASE_URL} o el valor guardado con 'config set-url').",
)
@click.option("--timeout", default=30, show_default=True, help="Timeout de red en segundos.")
@click.pass_context
def cli(ctx, base_url, timeout):
    """CLI de Genomic Hub: sincroniza, busca y descarga secuencias desde la terminal."""
    cfg = load_config()
    url = base_url or cfg.get("base_url", DEFAULT_BASE_URL)
    ctx.obj = {"client": GenomicHubClient(base_url=url, timeout=timeout)}


# =========================================
# CONFIG
# =========================================
@cli.group()
def config():
    """Configuración persistente del CLI (URL base, etc.)."""


@config.command("set-url")
@click.argument("url")
def config_set_url(url):
    """Guarda la URL base de la API para no tener que pasar --base-url siempre."""
    cfg = load_config()
    cfg["base_url"] = url.rstrip("/")
    save_config(cfg)
    click.echo(f"URL base guardada: {cfg['base_url']}")


@config.command("show")
def config_show():
    """Muestra la configuración actual."""
    cfg = load_config()
    click.echo(f"base_url: {cfg.get('base_url', DEFAULT_BASE_URL)}")


# =========================================
# SYNC
# =========================================
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
@click.option(
    "--from-file",
    type=click.Path(exists=True, dir_okay=False),
    help="Archivo de texto con un project_id por línea (se combina con los args si los hay).",
)
@click.option("--poll/--no-poll", default=True, help="Esperar y mostrar el resultado de la tarea.")
@click.pass_context
def sync_bulk(ctx, project_ids, from_file, poll):
    """Sincroniza varios PROJECT_IDS (máximo 120 por el límite del backend para este canal)."""
    client = get_client(ctx)

    ids = list(project_ids)
    if from_file:
        with open(from_file) as f:
            ids.extend(line.strip() for line in f if line.strip())

    # Dedup preservando orden
    seen = set()
    ids = [x for x in ids if not (x in seen or seen.add(x))]

    if not ids:
        click.secho("No se proporcionó ningún project_id.", fg="red")
        sys.exit(1)

    if len(ids) > MAX_BULK_IDS:
        click.secho(
            f"✗ Se recibieron {len(ids)} IDs, el máximo permitido es {MAX_BULK_IDS}.\n"
            f"  Divide la lista en lotes de {MAX_BULK_IDS} o menos.",
            fg="red",
        )
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


# =========================================
# BÚSQUEDA / CHECK
# =========================================
@cli.command("check")
@click.argument("target_id")
@click.pass_context
def check(ctx, target_id):
    """Verifica si TARGET_ID ya existe en la base local."""
    client = get_client(ctx)
    try:
        result = client.check(target_id)
        exists = result["exists_locally"]
        color = "green" if exists else "yellow"
        click.secho(f"{target_id}: {'ya existe localmente' if exists else 'no existe localmente'}", fg=color)
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@cli.command("search")
@click.argument("target_id")
@click.pass_context
def search(ctx, target_id):
    """Obtiene el árbol de datos local para TARGET_ID."""
    client = get_client(ctx)
    try:
        result = client.search(target_id)
        click.echo_via_pager(pretty_json(result["data"])) if click.confirm(
            "¿Mostrar con pager? (útil si la salida es larga)", default=False
        ) else click.echo(pretty_json(result["data"]))
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@cli.command("explore")
@click.argument("query")
@click.option("--page", default=1, show_default=True)
@click.option("--page-size", default=20, show_default=True)
@click.pass_context
def explore(ctx, query, page, page_size):
    """Busca BioProjects en NCBI por texto libre (QUERY)."""
    client = get_client(ctx)
    try:
        result = client.explore(query, page, page_size)
        click.echo(f"Total: {result['total']} resultados (página {result['page']})\n")
        for r in result["results"]:
            click.echo(f"  {r['bioproject_accession']:<15} {r.get('organism') or '-':<25} {r.get('title') or ''}")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@cli.command("task")
@click.argument("task_id")
@click.option("--poll/--no-poll", default=False, help="Esperar hasta que la tarea termine.")
@click.pass_context
def task_status(ctx, task_id, poll):
    """Consulta el estado de una tarea asíncrona TASK_ID."""
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
# DESCARGA (flujo OTP completo)
# =========================================
@cli.command("download")
@click.argument("run_id")
@click.option("--email", prompt="Email autorizado", help="Email registrado en la whitelist.")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Ruta de salida del archivo (default: nombre original en el directorio actual).",
)
@click.pass_context
def download(ctx, run_id, email, output):
    """
    Flujo completo de descarga para RUN_ID (ej. SRR1972976):

    1. Solicita el OTP al email
    2. Pide al usuario el código recibido
    3. Verifica el OTP e inicia la descompresión/preparación
    4. Espera a que el archivo esté listo
    5. Descarga el archivo
    """
    client = get_client(ctx)

    try:
        click.echo(f"Solicitando descarga de {run_id} para {email}...")
        req = client.request_download(run_id, email)
        click.secho("✓ Solicitud creada. Revisa tu correo para el código OTP.", fg="green")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)

    otp_code = click.prompt("Código OTP recibido")

    try:
        click.echo("Verificando código...")
        verify_result = client.verify_otp(run_id, email, otp_code)
        click.secho(f"✓ OTP verificado. task_id={verify_result['task_id']}", fg="green")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)

    click.echo("Esperando a que el archivo esté listo...")
    final = poll_task(client, verify_result["task_id"], label="Preparando archivo", show_result=False)
    if final is None or final.get("status") == "error":
        click.secho("✗ La tarea de preparación del archivo falló o no terminó a tiempo.", fg="red")
        sys.exit(1)

    try:
        click.echo("Descargando archivo...")
        saved_path = client.download_file(run_id, email, output_path=output)
        click.secho(f"✓ Archivo guardado en: {saved_path}", fg="green")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@cli.command("register-email")
@click.option("--admin-id", type=int, required=True, help="ID del admin que registra el correo (requiere permisos).")
@click.option("--name", required=True)
@click.option("--email", required=True)
@click.pass_context
def register_email(ctx, admin_id, name, email):
    """Registra un nuevo email autorizado bajo un admin (operación administrativa)."""
    client = get_client(ctx)
    try:
        result = client.register_email(admin_id, name, email)
        click.secho(f"✓ Email registrado. id_email={result['id_email']}", fg="green")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


# =========================================
# Helpers
# =========================================
# pretty_json, print_api_error y poll_task ahora viven en utils.py


if __name__ == "__main__":
    cli()
