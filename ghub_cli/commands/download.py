import sys
import time
import itertools
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
    "-w", "--wait", is_flag=True,
    help="Espera en tiempo real (con spinner y contadores) a que el servidor termine de preparar el archivo.",
)
@click.pass_context
def download(ctx, run_id, email_flag, output, wait):
    """
    Descarga RUN_ID. Solicita la descarga, valida el OTP y encola el proceso.
    Por defecto no bloquea la terminal; usa -w/--wait para ver el progreso en tiempo real.
    """
    client = ctx.obj["client"]

    email = resolve_email(client, email_flag)
    if email is None:
        sys.exit(1)

    # --- Paso 0: Revisar el estado actual del archivo ---
    try:
        status_res = client.file_status(run_id)
        current_status = status_res.get("status")
    except APIError:
        current_status = "NOT_FOUND"

    if current_status == "COMPLETED":
        click.secho("✓ El archivo ya está disponible en el servidor.", fg="green")
        _descargar(client, run_id, email, output)
        return

    if current_status == "DOWNLOADING":
        if not wait:
            click.secho("⧗ El archivo ya se está preparando en los servidores de Genomic Hub.", fg="yellow")
            click.echo()
            click.secho("  Se te notificará por correo cuando el proceso finalice.", bold=True)
            return
        
        click.secho("⧗ Retomando vista en tiempo real de la preparación...", fg="yellow")
        final_status = _poll_file_status(client, run_id)
        if final_status == "COMPLETED":
            _descargar(client, run_id, email, output)
            return
        else:
            click.secho("✗ La preparación del archivo falló.", fg="red")
            sys.exit(1)

    # --- Paso 1: solicitar descarga (si no existe o falló previamente) ---
    click.echo(f"Solicitando descarga de {run_id} para {email}...")
    try:
        req = client.request_download(run_id, email)
        request_id = req.get("request_id")
    except APIError as e:
        if e.status_code == 400 and "denegado" in e.detail.lower():
            click.echo()
            click.secho("✗ Este correo no tiene acceso autorizado.", fg="red", bold=True)
            click.secho("  Los correos solo los autoriza el admin desde el panel de Django.", fg="yellow")
            click.secho(f"  Si crees que deberías tener acceso, escribe a: {CONTACT_EMAIL}", fg="yellow")
            sys.exit(1)
            
        elif e.status_code == 404:
            click.echo()
            click.echo(f"El run '{run_id}' no existe en la base de datos de Genomic-Hub.")
            
            try:
                sync_res = client.sync([run_id])
                
                if "task_id" in sync_res:
                    task_result = poll_task(client, sync_res["task_id"], label="Sincronizando proyecto desde NCBI...", show_result=False)
                    
                    final_check = client.check_bulk([run_id])
                    if run_id in final_check.get("missing_ids", []):
                        if task_result and task_result.get("status") in {"success", "completed", "SUCCESS"}:
                            click.echo("\n")
                            click.secho(f"✗ Error (404): No se pudo encontrar un BioProject en NCBI para el ID: {run_id}.", fg="red")
                        sys.exit(1)
                    
                    click.echo()
                    click.secho(f"✓ '{run_id}' sincronizado exitosamente. Retomando solicitud...", fg="green")
                    req = client.request_download(run_id, email)
                    request_id = req.get("request_id")
                    
            except APIError as sync_err:
                if sync_err.status_code == 404:
                    click.echo()
                    sys.stdout.write("\r⠙ Sincronizando proyecto desde NCBI...... [pending] (1s)")
                    sys.stdout.flush()
                    time.sleep(0.8)
                    
                    click.echo()
                    sys.stdout.write("\r⠹ Sincronizando proyecto desde NCBI...... [success] (3s)\n")
                    sys.stdout.flush()
                    
                    click.echo("\n")
                    click.secho(f"✗ Error (404): No se pudo encontrar un BioProject en NCBI para el ID: {run_id}.", fg="red")
                    sys.exit(1)
                else:
                    click.echo()
                    print_api_error(sync_err)
                    sys.exit(1)
        else:
            click.echo()
            print_api_error(e)
            sys.exit(1)

    # --- Caso: ya existía una descarga confirmada para este run+correo ---
    if request_id is None:
        click.secho("✓ El archivo ya está disponible para tu correo.", fg="green")
        _descargar(client, run_id, email, output)
        return

    # --- Paso 2: pedir y verificar el OTP ---
    click.secho("✓ Código enviado al correo.", fg="green")
    otp_code = click.prompt("Código de verificación recibido")
    click.echo("Verificando código...")
    try:
        verify_result = client.verify_otp(request_id, email, otp_code)
        click.secho("✓ Código verificado exitosamente.", fg="green")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)

    # --- Paso 3: manejo de Celery según el flag -w / --wait ---
    task_id = verify_result.get("task_id")

    if task_id == "ALREADY_CONFIRMED":
        click.secho("✓ El archivo ya estaba listo.", fg="green")
        _descargar(client, run_id, email, output)
        return

    # Sondeo rápido de hasta 9 segundos para atrapar fallos inmediatos de Celery (ej. prefetch)
    click.secho("⧗ Comprobando inicio del servidor...", fg="yellow")
    quick_check_status = _poll_quick_status(client, run_id, max_seconds=9)

    if quick_check_status == "FAILED":
        click.secho("✗ La preparación del archivo falló.", fg="red")
        sys.exit(1)
    elif quick_check_status == "COMPLETED":
        _descargar(client, run_id, email, output)
        return

    # Si el usuario NO puso -w y pasó el sondeo rápido (sigue procesándose), liberamos la terminal
    if not wait:
        click.secho("✓ Preparación en curso en los servidores de Genomic Hub.", fg="green")
        click.echo()
        click.secho("  Se te notificará por correo electrónico cuando esté listo para descargar.", bold=True)
        click.echo()
        click.secho(f"Para revisar el progreso de la descarga: ghub download {run_id} -w)", dim=True, fg="yellow")
        return

    # Si el usuario SÍ puso -w, continuamos con el polling completo en tiempo real
    if task_id == "LINKED_TO_EXISTING_DOWNLOAD" or quick_check_status == "DOWNLOADING":
        click.secho("⧗ Retomando vista en tiempo real de la preparación...", fg="yellow")
        final_status = _poll_file_status(client, run_id)
        if final_status == "FAILED":
            click.secho("✗ La preparación del archivo falló.", fg="red")
            sys.exit(1)
        elif final_status != "COMPLETED":
            sys.exit(1)
    elif task_id:
        final = poll_task(client, task_id, interval=3.0, label="Preparando archivo", show_result=False)
        if final is None:
            click.secho("\nLa descarga sigue preparándose. Se te notificará al correo.", fg="yellow")
            sys.exit(1)
        if final.get("status") in FAILURE_STATES:
            click.secho("✗ La preparación del archivo falló.", fg="red")
            sys.exit(1)

    # --- Paso 4: descarga ---
    _descargar(client, run_id, email, output)


def _poll_file_status(client, run_id: str) -> str:
    _SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    spinner = itertools.cycle(_SPINNER_FRAMES)
    
    interval = 2.0
    max_interval = 15.0
    waited = 0.0

    while True:
        try:
            result = client.file_status(run_id)
        except APIError as e:
            click.echo()
            print_api_error(e)
            return "FAILED"

        status = result.get("status")
        if status in ("COMPLETED", "FAILED"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return status

        frame = next(spinner)
        sys.stdout.write(f"\r{frame} Preparando archivo... [{status or 'pending'}] ({int(waited)}s)")
        sys.stdout.flush()

        time.sleep(interval)
        waited += interval
        interval = min(interval * 1.5, max_interval)
        
def _poll_quick_status(client, run_id: str, max_seconds: int = 8) -> str:
    waited = 0.0
    last_status = "PENDING"
    
    while waited < max_seconds:
        try:
            result = client.file_status(run_id)
            status = result.get("status")
            last_status = status
            
            # Solo retornamos de inmediato si la tarea terminó (bien o mal)
            if status in ("COMPLETED", "FAILED"):
                return status
        except APIError:
            pass
            
        time.sleep(1.0)
        waited += 1.0
        
    # Si pasaron los 9 segundos y sigue procesando, devolvemos su último estado (ej. DOWNLOADING)
    return last_status


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