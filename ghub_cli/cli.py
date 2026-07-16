import click

from ghub_cli.core.config import load_config, save_config, DEFAULT_BASE_URL
from ghub_cli.core.client import GenomicHubClient

# La cuarentena (Menús Legacy)
from ghub_cli.commands.interactive import main_menu

# Comandos puros
from ghub_cli.commands.search import search, check, explore
from ghub_cli.commands.export import export_metadata
from ghub_cli.commands.download import download


@click.group(invoke_without_command=True)
@click.option("--base-url", default=None, help=f"URL base de la API (default: {DEFAULT_BASE_URL}).")
@click.option("--timeout", default=30, show_default=True, help="Timeout de red en segundos.")
@click.pass_context
def cli(ctx, base_url, timeout):
    """Genomic Hub CLI — consulta y descarga de secuencias genómicas."""
    
    cfg = load_config()
    url = base_url or cfg.get("base_url", DEFAULT_BASE_URL)
    ctx.ensure_object(dict)
    ctx.obj["client"] = GenomicHubClient(base_url=url, timeout=timeout)

    # Si se ejecuta 'ghub' sin argumentos, activamos el menú legacy
    if ctx.invoked_subcommand is None:
        main_menu(ctx)


# =========================================
# Subcomandos de Configuración
# =========================================
@cli.group()
def config():
    """Configuración persistente del CLI."""
    pass

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


# =========================================
# Registro de Comandos al CLI
# =========================================
cli.add_command(search)
cli.add_command(check)
cli.add_command(explore)
cli.add_command(export_metadata)
cli.add_command(download)


if __name__ == "__main__":
    cli()