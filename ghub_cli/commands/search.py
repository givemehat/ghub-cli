import sys
import re
import math
import click

from ghub_cli.core.client import APIError
from ghub_cli.utils.identifiers import detect_id_type
from ghub_cli.utils.formatters import pretty_json, print_api_error, print_formatted_search_results, print_formatted_explore_results
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
        
    if not as_json:
        click.echo(f"Enviando para consulta {len(target_ids)} ID(s)...")

    try:
        check_res = client.check_bulk(target_ids)
        missing = check_res.get("missing_ids", [])
        
        if missing:
            try:
                sync_res = client.sync(missing)
                
                if "task_id" in sync_res:
                    master_task_id = sync_res["task_id"]
                    poll_task(client, master_task_id, label="Sincronizando proyectos faltantes...", show_result=False)
                else:
                    # Respuesta síncrona/instantánea: renderizado idéntico sin sleeps
                    if not as_json:
                        click.echo()
                        click.echo("⠋ Sincronizando proyectos faltantes...... [pending] (0s)")
                        click.echo("⠙ Sincronizando proyectos faltantes...... [success] (0s)")
            except APIError as sync_err:
                if sync_err.status_code == 404:
                    # Fast-Fail del backend para 1 ID: renderizado idéntico sin sleeps
                    if not as_json:
                        click.echo()
                        click.echo("⠋ Sincronizando proyectos faltantes...... [pending] (0s)")
                        click.echo("⠙ Sincronizando proyectos faltantes...... [success] (0s)")
                else:
                    raise sync_err
            
            # Hacemos un segundo chequeo exclusivamente sobre los IDs que intentamos sincronizar
            final_check = client.check_bulk(missing)
            failed_ids = final_check.get("missing_ids", [])
            
            # Si después de todo aún siguen faltando, los mostramos con tu formato exacto asegurando mayúsculas
            if failed_ids and not as_json:
                click.echo()
                click.secho(f"✗ Fallo de sincronización: {', '.join([f.upper() for f in failed_ids])}", fg="yellow")
            
            if not as_json:
                click.echo()

        projects = [i for i in target_ids if detect_id_type(i) in ["bioproject", "geo_series", "study"]]
        samples = [i for i in target_ids if detect_id_type(i) in ["sample", "biosample", "geo_sample"]]
        experiments = [i for i in target_ids if detect_id_type(i) in ["experiment", "geo_platform"]]
        runs = [i for i in target_ids if detect_id_type(i) in ["run"]]

        final_data = []

        if projects:
            res = client.get_bioprojects_batch(projects, page, page_size)
            items = res.get("data", [])
            for item in items:
                item["_cli_type"] = "bioproject"
                item_total = item.get("total_items", len(item.get("experiments", [])))
                item["pagination"] = {"page": page, "page_size": page_size, "total_items": item_total}
            final_data.extend(items)

        if samples and page == 1:
            res = client.get_samples_batch(samples)
            items = res.get("data", [])
            for item in items:
                item["_cli_type"] = "sample"
            final_data.extend(items)

        if experiments:
            res = client.get_experiments_batch(experiments, page, page_size)
            items = res.get("data", [])
            for item in items:
                item["_cli_type"] = "experiment"
                for exp in item.get("experiments", []):
                    exp_total = exp.get("total_items", len(exp.get("runs", [])))
                    exp["pagination"] = {"page": page, "page_size": page_size, "total_items": exp_total}
            final_data.extend(items)

        if runs and page == 1:
            res = client.get_runs_batch(runs)
            items = res.get("data", [])
            for item in items:
                item["_cli_type"] = "run"
            final_data.extend(items)

        if as_json:
            click.echo(pretty_json(final_data))
        else:
            print_formatted_search_results(final_data)

        return final_data

    except APIError as e:
        print_api_error(e)
        sys.exit(1)


@click.command("explore")
@click.argument("query")
@click.option("--page", default=1, show_default=True, help="Número de página.")
@click.option("--page-size", default=20, show_default=True, help="Elementos por página.")
@click.option("--ids", "-i", is_flag=True, help="Muestra únicamente los IDs de los BioProjects encontrados.")
@click.option("--json", "as_json", is_flag=True, help="Muestra el resultado en JSON crudo.")
@click.pass_context
def explore(ctx, query, page, page_size, ids, as_json):
    """Busca BioProjects en NCBI por texto libre."""
    client = ctx.obj.get("client") if ctx.obj else GenomicHubClient()
    
    try:
        if not as_json and not ids:
            click.echo(f"Buscando en NCBI: '{query}'...")

        result = client.explore(query, page, page_size)

        if as_json:
            click.echo(pretty_json(result))
            return

        items = result.get("data", [])
        
        if ids:
            for r in items:
                accession = r.get("bioproject_accession")
                if accession:
                    click.echo(accession)
            return

        total_items = result.get("total_items", len(items))
        current_page = result.get("page", page)

        click.echo()

        pagination = {
            "page": current_page,
            "page_size": page_size,
            "total_items": total_items
        }

        print_formatted_explore_results(items, pagination)

    except APIError as e:
        print_api_error(e)
        sys.exit(1)