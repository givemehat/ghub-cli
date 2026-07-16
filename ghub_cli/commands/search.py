import sys
import re
import click

from ghub_cli.core.client import APIError
from ghub_cli.utils.identifiers import detect_id_type
from ghub_cli.utils.formatters import pretty_json, print_api_error, print_formatted_search_results
from ghub_cli.utils.tasks import poll_task, FAILURE_STATES

MAX_BULK_IDS = 120

def get_client(ctx):
    return ctx.obj["client"]

@click.command("search")
@click.argument("raw_ids", nargs=-1, required=True)
@click.option("--page", default=1, show_default=True, help="Número de página a mostrar.")
@click.option("--page-size", default=20, show_default=True, help="Resultados por página.")
@click.option("--json", "as_json", is_flag=True, help="Muestra los resultados en JSON crudo.")
@click.pass_context
def search(ctx, raw_ids, page, page_size, as_json):
    """Orquesta de búsqueda: Verifica, Sincroniza y Consulta."""
    client = get_client(ctx)
    
    joined_input = " ".join(raw_ids)
    cleaned_input = re.sub(r'[\[\],;]', ' ', joined_input)
    target_ids = list(dict.fromkeys(cleaned_input.split()))

    if not target_ids:
        click.secho("✗ No se detectaron IDs válidos.", fg="red")
        sys.exit(1)

    if len(target_ids) > MAX_BULK_IDS:
        click.secho(f"✗ Máximo {MAX_BULK_IDS} IDs por solicitud (recibidos {len(target_ids)}).", fg="red")
        sys.exit(1)

    try:
        check_res = client.check_bulk(target_ids)
        missing = check_res.get("missing_ids", [])
        
        if missing:
            if not as_json:
                click.secho(f"Sincronizando {len(missing)} ID(s) faltantes en NCBI...", fg="yellow")
            
            sync_res = client.sync(missing)
            
            if "task_id" in sync_res:
                master_task_id = sync_res["task_id"]
                final_state = poll_task(client, master_task_id, label="Planificando descargas...", show_result=False)
                
                if final_state and final_state.get("status") not in FAILURE_STATES:
                    sub_tasks = final_state.get("data", [])
                    if isinstance(sub_tasks, list):
                        for i, sub in enumerate(sub_tasks):
                            if isinstance(sub, dict) and "task_id" in sub:
                                poll_task(client, sub["task_id"], label=f"Sincronizando ({i+1}/{len(sub_tasks)})...", show_result=False)
                else:
                    click.secho("\n✗ La sincronización en lote falló.", fg="red")
                    sys.exit(1)
            
            if not as_json:
                click.echo()

        projects = [i for i in target_ids if detect_id_type(i) in ["bioproject", "geo_series", "study"]]
        samples = [i for i in target_ids if detect_id_type(i) in ["sample", "biosample", "geo_sample"]]
        experiments = [i for i in target_ids if detect_id_type(i) in ["experiment", "geo_platform"]]
        runs = [i for i in target_ids if detect_id_type(i) in ["run"]]

        final_data = []
        total_items = 0

        if projects:
            res = client.get_bioprojects_batch(projects, page, page_size)
            final_data.extend(res.get("data", []))
            total_items = max(total_items, res.get("total_items", 0))
            
        if samples:
            res = client.get_samples_batch(samples)
            final_data.extend(res.get("data", []))
            total_items = max(total_items, len(res.get("data", [])))
            
        if experiments:
            res = client.get_experiments_batch(experiments, page, page_size)
            final_data.extend(res.get("data", []))
            total_items = max(total_items, res.get("total_items", 0))
            
        if runs:
            res = client.get_runs_batch(runs)
            final_data.extend(res.get("data", []))
            total_items = max(total_items, len(res.get("data", [])))

        if as_json:
            click.echo(pretty_json(final_data))
        else:
            print_formatted_search_results(final_data, page, page_size, total_items, len(target_ids))
        
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@click.command("check")
@click.argument("raw_ids", nargs=-1, required=True)
@click.pass_context
def check(ctx, raw_ids):
    """Verifica masivamente si los IDs existen en la base local."""
    client = get_client(ctx)
    joined_input = " ".join(raw_ids)
    cleaned_input = re.sub(r'[\[\],;]', ' ', joined_input)
    target_ids = list(dict.fromkeys(cleaned_input.split()))

    if len(target_ids) > MAX_BULK_IDS:
        click.secho(f"✗ Máximo {MAX_BULK_IDS} IDs por solicitud.", fg="red")
        sys.exit(1)

    try:
        click.echo(f"Verificando {len(target_ids)} ID(s)...")
        result = client.check_bulk(target_ids)
        click.echo()
        if result.get("existing_ids"):
            click.secho("✓ Registered in Genomic-Hub:", fg="green", bold=True)
            for eid in result["existing_ids"]:
                click.secho(f"  - {eid}", fg="green")
                
        if result.get("missing_ids"):
            click.secho("\n✗ Not found in Genomic-Hub (sync required):", fg="yellow", bold=True)
            for mid in result["missing_ids"]:
                click.secho(f"  - {mid}", fg="yellow")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@click.command("explore")
@click.argument("query")
@click.option("--page", default=1, show_default=True)
@click.option("--page-size", default=20, show_default=True)
@click.pass_context
def explore(ctx, query, page, page_size):
    """Busca BioProjects en NCBI por texto libre."""
    client = get_client(ctx)
    try:
        result = client.explore(query, page, page_size)
        click.echo(f"Total: {result['total_items']} resultados (página {result['page']})\n")
        for r in result["data"]:
            click.echo(f"  {r['bioproject_accession']:<15} {r.get('organism') or '-':<25} {r.get('title') or ''}")
    except APIError as e:
        print_api_error(e)
        sys.exit(1)