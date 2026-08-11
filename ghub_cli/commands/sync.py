from __future__ import annotations

import sys
import click
from ghub_cli.core.client import GenomicHubClient, APIError
from ghub_cli.utils.formatters import pretty_json, print_api_error
from ghub_cli.utils.tasks import poll_task

@click.command("sync")
@click.argument("raw_ids", nargs=-1, required=True)
@click.option("--wait", "-w", is_flag=True, help="Espera a que termine el proceso de sincronización en segundo plano.")
@click.option("--json", "as_json", is_flag=True, help="Muestra el resultado en JSON crudo.")
@click.pass_context
def sync(ctx, raw_ids, wait, as_json):
    """Sincroniza uno o más IDs desde NCBI hacia los servidores de Genomic-Hub."""
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
            click.echo(f"Enviando para sincronización {len(target_ids)} ID(s)...")

        sync_res = client.sync(target_ids)

        if as_json:
            click.echo(pretty_json(sync_res))
            return

        task_id = sync_res.get("task_id")

        if not task_id:
            # Fallback de seguridad por si el backend responde éxito pero sin tarea
            click.echo("✓ Solicitud de sincronización procesada.")
            return

        if wait:
            # Guardamos el resultado de poll_task, sin detener el código si ocurre un 500
            # (Eliminamos el click.echo() previo para evitar el doble salto de línea)
            task_result = poll_task(client, task_id, label="Sincronizando proyectos...", show_result=False)
            
            # Siempre hacemos el chequeo final para listar exactamente qué falló y qué funcionó
            final_check = client.check_bulk(target_ids)
            failed_ids = final_check.get("missing_ids", [])
            success_ids = final_check.get("existing_ids", [])

            # 1. MOVIDO: Mostramos el error 404 justo después del spinner si hubo fallos
            if failed_ids and task_result and task_result.get("status") in {"success", "completed", "SUCCESS"}:
                click.secho("✗ Error (404): No se encontró un registro válido en NCBI para algún ID.", fg="red")
                click.echo()
            elif task_result:
                # Si no hubo error pero terminó el spinner, dejamos un salto para separar de las listas
                click.echo()

            # 2. Mostramos los IDs exitosos
            if success_ids:
                click.secho("✓ Sincronizados con éxito:", bold=True, fg="green")
                for eid in success_ids:
                    click.echo(f"  - {eid}")
                click.echo()

            # 3. Mostramos los IDs que fallaron
            if failed_ids:
                click.secho("✗ Fallo de sincronización:", bold=True, fg="red")
                for mid in failed_ids:
                    click.echo(f"  - {mid}")
                click.echo()
        else:
            # Comportamiento rápido por defecto con la nota informativa
            click.echo()
            click.echo("Sincronización iniciada en segundo plano. Puede tardar unos minutos en completarse.\n")
            click.secho("Para ver el proceso completo: ghub sync [IDs] --wait (-w)", fg="yellow", bold=True)

    except APIError as e:
        # Imprime el error de la API (los rechazos instantáneos)
        click.echo()
        print_api_error(e)
        click.echo()
        
        # Mantiene la consistencia de la lista final
        click.secho("✗ Fallo de sincronización:", bold=True, fg="red")
        for tid in target_ids:
            click.echo(f"  - {tid.upper()}")
        click.echo()
        sys.exit(1)