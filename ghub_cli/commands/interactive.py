import sys
import click

from ghub_cli.core.config import load_config, save_config
from ghub_cli.core.client import APIError
from ghub_cli.utils.formatters import print_api_error
from ghub_cli.utils.tasks import poll_task, FAILURE_STATES
from ghub_cli.commands.search import search

CONTACT_EMAIL = "leticiavega@icar.unam.mx"

def _save_email(cfg: dict, email: str):
    cfg["email"] = email
    save_config(cfg)
    click.secho("  ✓ Correo guardado para futuras sesiones.", fg="green")

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

    option = click.prompt("Selecciona una opción", type=click.Choice(["0", "1", "2"]), show_choices=False)

    if option == "0":
        click.echo("¡Hasta luego!")
        sys.exit(0)
    elif option == "1":
        _search_menu(ctx)
    elif option == "2":
        _download_flow(ctx)

def _search_menu(ctx):
    click.echo("\n── Consulta ─────────────────────────────────────────")
    click.echo("\n  [1]  Buscar en NCBI por texto libre")
    click.echo("  [2]  Ver datos de un ID en Genomic-Hub")
    click.echo("  [3]  Verificar si un ID existe en Genomic-Hub")
    click.echo("  [0]  Volver al menú principal\n")

    option = click.prompt("Selecciona una opción", type=click.Choice(["0", "1", "2", "3"]), show_choices=False)
    client = ctx.obj["client"]

    if option == "0":
        main_menu(ctx)
        return
    elif option == "1":
        from ghub_cli.commands.search import explore
        query = click.prompt("Término de búsqueda")
        try:
            result = client.explore(query, page=1, page_size=20)
            click.echo(f"\n  Total: {result['total_items']} resultados\n")
            for r in result["data"]:
                click.echo(f"  {r.get('bioproject_accession', '-'):<15} {r.get('organism') or '-':<25} {r.get('title') or ''}")
        except APIError as e:
            print_api_error(e)
    elif option == "2":
        target_id = click.prompt("ID a consultar")
        click.echo()
        try:
            ctx.invoke(search, raw_ids=(target_id,), page=1, page_size=20)
        except SystemExit:
            pass
    elif option == "3":
        from ghub_cli.commands.search import check
        target_id = click.prompt("ID a verificar")
        try:
            result = client.check_bulk([target_id])
            exists = target_id in result.get("existing_ids", [])
            color = "green" if exists else "yellow"
            message = "✓ En Genomic-Hub" if exists else "✗ No encontrado en Genomic-Hub"
            click.secho(f"\n  {target_id}: {message}", fg=color)
        except APIError as e:
            print_api_error(e)

    click.echo()
    _search_menu(ctx)

def _download_flow(ctx):
    client = ctx.obj["client"]
    cfg = load_config()

    click.echo("\n── Descarga de secuencias ───────────────────────────\n")

    email = cfg.get("email")
    if email:
        click.echo(f"  Email registrado: {click.style(email, fg='green')}")
        if not click.confirm("  ¿Usar este email?", default=True):
            email = None

    if not email:
        email = click.prompt("  Ingresa tu correo institucional")
        click.echo("  Verificando acceso...")
        try:
            client.request_download("__check__", email)
            _save_email(cfg, email)
        except APIError as e:
            if e.status_code == 400 and "denegado" in e.detail.lower():
                click.secho("\n  ✗ Este correo no está registrado.", fg="red", bold=True)
                click.secho(f"  Para solicitar acceso escribe a: {CONTACT_EMAIL}", fg="yellow")
                if click.confirm("\n  ¿Intentar con otro correo?", default=True):
                    _download_flow(ctx)
                return
            elif e.status_code == 404 or "no existe" in e.detail.lower():
                _save_email(cfg, email)
            else:
                print_api_error(e)
                return

    run_id = click.prompt("\n  Ingresa el ID de la secuencia a descargar (ej. SRR1972976)")
    click.echo("\n  Solicitando código de verificación...")
    try:
        req = client.request_download(run_id, email)
        request_id = req.get("request_id")
    except APIError as e:
        if e.status_code == 400 and "denegado" in e.detail.lower():
            click.secho("  ✗ Tu correo ya no tiene acceso autorizado.", fg="red")
            cfg.pop("email", None)
            save_config(cfg)
        else:
            print_api_error(e)
        return

    if request_id is None:
        click.secho("  ✓ El archivo ya está disponible para tu correo.", fg="green")
        _execute_download(ctx, client, run_id, email)
        return

    otp_code = click.prompt("\n  Código de verificación recibido")
    click.echo("\n  Verificando código...")
    try:
        verify_result = client.verify_otp(request_id, email, otp_code)
        click.secho("  ✓ Código verificado. Iniciando preparación...", fg="green")
    except APIError as e:
        print_api_error(e)
        return

    task_id = verify_result.get("task_id")
    if task_id and task_id not in ("ALREADY_CONFIRMED", "LINKED_TO_EXISTING_DOWNLOAD"):
        final = poll_task(client, task_id, interval=3.0, label="Preparando archivo", show_result=False)
        if final is None:
            click.secho("\n  La descarga sigue preparándose. Retómala con:", fg="yellow")
            return
        if final.get("status") in FAILURE_STATES:
            click.secho("  ✗ La preparación del archivo falló.", fg="red")
            return
    else:
        click.secho("  ✓ El archivo ya estaba listo.", fg="green")

    _execute_download(ctx, client, run_id, email)


def _execute_download(ctx, client, run_id: str, email: str):
    output = click.prompt(
        "\n  Ruta de destino (Enter para usar el directorio actual)",
        default="", show_default=False
    ).strip() or None

    click.echo("  Descargando...")
    try:
        saved_path = client.download_file(run_id, email, output_path=output)
        click.secho(f"\n  ✓ Archivo guardado en: {saved_path}", fg="green", bold=True)
    except APIError as e:
        print_api_error(e)
        return

    if click.confirm("\n  ¿Volver al menú principal?", default=True):
        main_menu(ctx)