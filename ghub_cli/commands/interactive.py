import sys
import click

from ghub_cli.core.config import load_config, save_config
from ghub_cli.core.client import APIError
from ghub_cli.utils.formatters import print_api_error
from ghub_cli.utils.tasks import poll_task, FAILURE_STATES
from ghub_cli.commands.search import search

CONTACT_EMAIL = "leticiavega@icar.unam.mx"

def _guardar_email(cfg: dict, email: str):
    cfg["email"] = email
    save_config(cfg)
    click.secho(f"  ✓ Correo guardado para futuras sesiones.", fg="green")

def menu_principal(ctx):
    """Menú interactivo de bienvenida (Legacy)."""
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

def _menu_consulta(ctx):
    click.echo("\n── Consulta ─────────────────────────────────────────")
    click.echo("\n  [1]  Buscar en NCBI por texto libre")
    click.echo("  [2]  Ver datos locales de un ID (con auto-sincronización)")
    click.echo("  [3]  Verificar si un ID existe localmente")
    click.echo("  [0]  Volver al menú principal\n")

    opcion = click.prompt("Selecciona una opción", type=click.Choice(["0", "1", "2", "3"]), show_choices=False)
    client = ctx.obj["client"]

    if opcion == "0":
        menu_principal(ctx)
    elif opcion == "1":
        query = click.prompt("Término de búsqueda")
        try:
            result = client.explore(query, page=1, page_size=20)
            click.echo(f"\n  Total: {result['total']} resultados\n")
            for r in result["results"]:
                click.echo(f"  {r.get('bioproject_accession', '-'):<15} {r.get('organism') or '-':<25} {r.get('title') or ''}")
        except APIError as e:
            print_api_error(e)
    elif opcion == "2":
        target_id = click.prompt("ID a consultar")
        click.echo()
        ctx.invoke(search, raw_ids=(target_id,), page=1, page_size=20)
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
    if click.confirm("¿Volver al menú principal?", default=True):
        menu_principal(ctx)

def _flujo_descarga(ctx):
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
            _guardar_email(cfg, email)
        except APIError as e:
            if e.status_code == 400 and "denegado" in e.detail.lower():
                click.secho("\n  ✗ Este correo no está registrado.", fg="red", bold=True)
                click.secho(f"  Para solicitar acceso escribe a: {CONTACT_EMAIL}", fg="yellow")
                if click.confirm("\n  ¿Intentar con otro correo?", default=True):
                    _flujo_descarga(ctx)
                return
            elif e.status_code == 404 or "no existe" in e.detail.lower():
                _guardar_email(cfg, email)
            else:
                print_api_error(e)
                return

    run_id = click.prompt("\n  Ingresa el ID de la secuencia a descargar (ej. SRR1972976)")
    click.echo("\n  Solicitando código de verificación...")
    try:
        client.request_download(run_id, email)
        click.secho("  ✓ Código enviado a tu correo.", fg="green")
    except APIError as e:
        if e.status_code == 400 and "denegado" in e.detail.lower():
            click.secho("  ✗ Tu correo ya no tiene acceso autorizado.", fg="red")
            cfg.pop("email", None)
            save_config(cfg)
        else:
            print_api_error(e)
        return

    otp_code = click.prompt("\n  Código de verificación recibido")
    click.echo("\n  Verificando código...")
    try:
        verify_result = client.verify_otp(run_id, email, otp_code)
        click.secho("  ✓ Código verificado. Iniciando preparación...", fg="green")
    except APIError as e:
        print_api_error(e)
        return

    task_id = verify_result.get("task_id")
    if task_id and task_id not in ("ALREADY_CONFIRMED", "LINKED_TO_EXISTING_DOWNLOAD"):
        final = poll_task(client, task_id, interval=3.0, label="Preparando archivo", show_result=False)
        if final is None:
            click.secho("\n  La descarga sigue preparándose. Retómala con:", fg="yellow")
            click.secho(f"    ghub task {task_id} --poll", fg="yellow", bold=True)
            return
        if final.get("status") in FAILURE_STATES:
            click.secho("  ✗ La preparación del archivo falló.", fg="red")
            return
    else:
        click.secho("  ✓ El archivo ya estaba listo.", fg="green")

    output = click.prompt("\n  Ruta de destino (Enter para usar el directorio actual)", default="", show_default=False).strip() or None
    click.echo("  Descargando...")
    try:
        saved_path = client.download_file(run_id, email, output_path=output)
        click.secho(f"\n  ✓ Archivo guardado en: {saved_path}", fg="green", bold=True)
    except APIError as e:
        print_api_error(e)
        return

    if click.confirm("\n  ¿Volver al menú principal?", default=True):
        menu_principal(ctx)