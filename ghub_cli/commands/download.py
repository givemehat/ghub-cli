import sys
import click

from ghub_cli.core.client import APIError
from ghub_cli.utils.formatters import print_api_error, pretty_json
from ghub_cli.utils.tasks import poll_task
from ghub_cli.utils.email import resolve_email

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
@click.pass_context
def download(ctx, run_id, email_flag, output):
    """Descarga RUN_ID, sin pasar por el menú interactivo."""
    client = ctx.obj["client"]

    email = resolve_email(client, email_flag)
    if email is None:
        sys.exit(1)

    click.echo(f"  Verificando si el archivo ya está disponible para {email}...")
    try:
        saved_path = client.download_file(run_id, email, output_path=output)
        click.secho(f"✓ Archivo guardado en: {saved_path}", fg="green", bold=True)
    except APIError as e:
        print_api_error(e)
        if e.status_code == 404 or (e.status_code == 400 and "autorizaci" in e.detail.lower()):
            click.secho(
                "\n  Si ya hiciste el flujo de OTP para este run_id y solo se agotó el\n"
                "  tiempo de espera, corre: ghub task <task_id> --poll\n"
                "  Cuando termine, vuelve a correr este comando.", fg="yellow"
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