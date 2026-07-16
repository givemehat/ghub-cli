import sys
import click

from ghub_cli.core.client import APIError
from ghub_cli.utils.formatters import print_api_error
from ghub_cli.utils.tasks import poll_task, FAILURE_STATES

@click.command("download")
@click.argument("run_id")
@click.option("--email", required=True, help="Correo institucional ya registrado.")
@click.option("-o", "--output", default=None, help="Ruta de destino del archivo.")
@click.pass_context
def download(ctx, run_id, email, output):
    """Descarga RUN_ID para --email, sin pasar por el menú interactivo."""
    client = ctx.obj["client"]
    click.echo("  Verificando autorización y solicitando archivo...")
    
    try:
        req_res = client.request_download(run_id, email)
        request_id = req_res.get("request_id")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)
        
    if request_id is not None:
        click.secho("  ✓ Código enviado a tu correo.", fg="green")
        otp_code = click.prompt("  Código de verificación recibido")
        click.echo("  Verificando código...")
        try:
            verify_result = client.verify_otp(run_id, email, otp_code)
            click.secho("  ✓ Código verificado.", fg="green")
            task_id = verify_result.get("task_id")
            
            if task_id and task_id not in ("ALREADY_CONFIRMED", "LINKED_TO_EXISTING_DOWNLOAD"):
                final = poll_task(client, task_id, interval=3.0, label="Preparando archivo", show_result=False)
                if final is None:
                     click.secho(
                        "\n  Tiempo de espera agotado, pero el archivo puede seguir preparándose en el servidor.\n"
                        "  Intenta ejecutar este comando de descarga nuevamente en unos minutos.", fg="yellow"
                    )
                     sys.exit(1)
                if final.get("status") in FAILURE_STATES:
                    click.secho("  ✗ La preparación del archivo falló.", fg="red")
                    sys.exit(1)
        except APIError as e:
            print_api_error(e)
            sys.exit(1)
    else:
        click.secho("  ✓ Autorización confirmada. El archivo ya está listo.", fg="green")

    click.echo("  Descargando...")
    try:
        saved_path = client.download_file(run_id, email, output_path=output)
        click.secho(f"\n✓ Archivo guardado en: {saved_path}", fg="green", bold=True)
    except APIError as e:
        print_api_error(e)
        if e.status_code == 404 or (e.status_code == 400 and "autorizaci" in e.detail.lower()):
            click.secho(
                "\n  Si ya hiciste el flujo de verificación y la descarga falló o se interrumpió,\n"
                "  intenta ejecutar este comando nuevamente.", fg="yellow"
            )
        sys.exit(1)