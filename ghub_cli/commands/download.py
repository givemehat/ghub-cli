import sys
import click

from ghub_cli.core.client import APIError
from ghub_cli.utils.formatters import print_api_error, pretty_json
from ghub_cli.utils.tasks import poll_task, FAILURE_STATES
from ghub_cli.utils.email import resolve_email, CONTACT_EMAIL


@click.command("download")
@click.argument("run_id")
@click.option(
    "--email",
    "email_flag",
    default=None,
    help="Correo institucional. Si se omite, se usa el guardado "
         "(o se pide uno nuevo y se guarda). No sobrescribe el guardado.",
)
@click.option("-o", "--output", default=None, help="Ruta de destino del archivo.")
@click.option(
    "--no-poll", is_flag=True,
    help="Solo encola la preparación del archivo tras verificar el OTP, sin esperar a que termine.",
)
@click.pass_context
def download(ctx, run_id, email_flag, output, no_poll):
    """
    Descarga RUN_ID. Hace todo el flujo en un solo comando: resuelve el
    correo, solicita la descarga, pide el código OTP si hace falta,
    espera a que el archivo esté listo y lo descarga.
    """
    client = ctx.obj["client"]

    email = resolve_email(client, email_flag)
    if email is None:
        sys.exit(1)

    # --- Paso 1: solicitar descarga ---
    click.echo(f"Solicitando descarga de {run_id} para {email}...")
    try:
        req = client.request_download(run_id, email)
        request_id = req.get("request_id")
    except APIError as e:
        if e.status_code == 400 and "denegado" in e.detail.lower():
            click.secho("✗ Este correo no tiene acceso autorizado.", fg="red", bold=True)
            click.secho("  Los correos solo los autoriza el admin desde el panel de Django.", fg="yellow")
            click.secho(f"  Si crees que deberías tener acceso, escribe a: {CONTACT_EMAIL}", fg="yellow")
        elif e.status_code == 404:
            click.secho(f"✗ El run '{run_id}' no existe en la base de datos local.", fg="red", bold=True)
            click.secho(f"  Prueba sincronizarlo primero, ej: ghub search {run_id}", fg="yellow")
        else:
            print_api_error(e)
        sys.exit(1)

    # --- Caso: ya existía una descarga confirmada para este run+correo ---
    if request_id is None:
        click.secho("✓ El archivo ya está disponible para tu correo.", fg="green")
        _descargar(client, run_id, email, output)
        return

    # --- Paso 2: pedir y verificar el OTP ---
    click.secho("✓ Código enviado a tu correo.", fg="green")
    otp_code = click.prompt("Código de verificación recibido")
    click.echo("Verificando código...")
    try:
        verify_result = client.verify_otp(request_id, email, otp_code)
        click.secho("✓ Código verificado. Iniciando preparación...", fg="green")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)

    # --- Paso 3: esperar a que el backend prepare el archivo (Celery) ---
    task_id = verify_result.get("task_id")
    if task_id and task_id not in ("ALREADY_CONFIRMED", "LINKED_TO_EXISTING_DOWNLOAD"):
        if no_poll:
            click.secho(f"Tarea encolada: {task_id}", fg="yellow")
            click.secho(f"  Revisa el estado con: ghub task {task_id} --poll", fg="yellow")
            return

        final = poll_task(client, task_id, interval=3.0, label="Preparando archivo", show_result=False)
        if final is None:
            click.secho("\nLa descarga sigue preparándose. Retómala con:", fg="yellow")
            click.secho(f"  ghub task {task_id} --poll", fg="yellow", bold=True)
            click.secho(f"  y luego vuelve a correr: ghub download {run_id} --email {email}", fg="yellow")
            sys.exit(1)
        if final.get("status") in FAILURE_STATES:
            click.secho("✗ La preparación del archivo falló.", fg="red")
            sys.exit(1)
    else:
        click.secho("✓ El archivo ya estaba listo.", fg="green")

    # --- Paso 4: descarga ---
    _descargar(client, run_id, email, output)


def _descargar(client, run_id: str, email: str, output: str):
    click.echo("Descargando...")
    try:
        saved_path = client.download_file(run_id, email, output_path=output)
        click.secho(f"✓ Archivo guardado en: {saved_path}", fg="green", bold=True)
    except APIError as e:
        print_api_error(e)
        if e.status_code == 404 or (e.status_code == 400 and "autorizaci" in e.detail.lower()):
            click.secho(
                "\n  Si ya hiciste el flujo de verificación y la descarga falló o se interrumpió,\n"
                "  intenta ejecutar este comando nuevamente.", fg="yellow"
            )
        sys.exit(1)


@click.command("task")
@click.argument("task_id")
@click.option("--poll/--no-poll", default=False)
@click.pass_context
def task_status(ctx, task_id, poll):
    """Consulta el estado de una tarea asíncrona."""
    client = ctx.obj["client"]
    try:
        if poll:
            poll_task(client, task_id)
        else:
            result = client.task_status(task_id)
            click.echo(pretty_json(result))
    except APIError as e:
        print_api_error(e)
        sys.exit(1)