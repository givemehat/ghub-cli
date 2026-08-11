from __future__ import annotations

import sys
import click
from ghub_cli.core.client import GenomicHubClient, APIError
from ghub_cli.utils.formatters import pretty_json, print_api_error

@click.command("check")
@click.argument("raw_ids", nargs=-1, required=True)
@click.option("--json", "as_json", is_flag=True, help="Muestra los resultados en JSON crudo.")
@click.pass_context
def check(ctx, raw_ids, as_json):
    """Verifica el estado de existencia de uno o más IDs en Genomic-Hub."""
    client = ctx.obj.get("client") if ctx.obj else GenomicHubClient()
    
    import re
    joined_input = " ".join(raw_ids)
    cleaned_input = re.sub(r'[\[\],;]', ' ', joined_input)
    target_ids = list(dict.fromkeys(cleaned_input.split()))

    if not target_ids:
        click.echo("✗ No se detectaron IDs válidos.")
        sys.exit(1)

    try:
        if not as_json:
            click.echo(f"Enviando para verificación {len(target_ids)} ID(s)...")
            click.echo()

        check_res = client.check_bulk(target_ids)
        
        if as_json:
            click.echo(pretty_json(check_res))
            return

        existing = check_res.get("existing_ids", [])
        missing = check_res.get("missing_ids", [])

        if existing:
            click.secho("✓ Existentes en Genomic-Hub:", bold=True, fg="green")
            for eid in existing:
                click.echo(f"  - {eid}")
            click.echo()

        if missing:
            click.secho("✗ Faltantes (requieren sincronización):", bold=True, fg="red")
            for mid in missing:
                click.echo(f"  - {mid}")
            click.echo()

        
        if missing:
            click.secho("Nota: La verificación se realiza en los servidores de Genomic-Hub (no se valida en NCBI).", bold=True, fg="yellow")
            click.secho("Para sincronizar: ghub sync [IDs]", bold=True, fg="yellow")

    except APIError as e:
        print_api_error(e)
        sys.exit(1)