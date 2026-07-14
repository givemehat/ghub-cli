import json
import math
import click
from ghub_cli.core.client import APIError

def pretty_json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)

def print_api_error(e: APIError) -> None:
    click.secho(f"✗ Error ({e.status_code}): {e.detail}", fg="red")
    if e.code:
        click.secho(f"  code: {e.code}", fg="red", dim=True)

def print_formatted_search_results(data_list, page, page_size, total_items, ids_procesados):
    if not data_list:
        click.secho("No se encontraron datos.", fg="yellow")
        return

    click.echo()
    tipo_vista = "genérico"
    
    for idx, item in enumerate(data_list):
        if idx > 0:
            click.echo("\n" + "═" * 80 + "\n")
        else:
            click.echo("═" * 80)

        if "bioproject_accession" in item:
            tipo_vista = "bioproject"
            _print_bioproject(item)
        elif "sample_accession" in item:
            tipo_vista = "sample"
            _print_sample(item)
        elif "run_accession" in item:
            tipo_vista = "run"
            _print_run(item)
        elif "bioproject" in item and "experiments" in item:
            tipo_vista = "experiment"
            _print_experiment(item)
        else:
            click.secho("Ítem genérico", bold=True)
            click.echo(pretty_json(item))

    # Imprimir siempre la línea de cierre al final del bucle para todas las vistas
    click.echo("═" * 80)

    # La metadata de paginación se queda exclusiva de BioProject y Experiment
    if tipo_vista not in ["sample", "run"]:
        paginas_totales = math.ceil(total_items / page_size) if page_size > 0 else 1
        click.secho(f"Página {page} de {paginas_totales} ({page_size} items por página)", dim=True)
        click.echo("═" * 80)


# =========================================
# Funciones Auxiliares
# =========================================

def _render_bioproject_block(proj_dict, include_pubs=False):
    p_acc = proj_dict.get("bioproject_accession", "PROYECTO_DESCONOCIDO")
    p_title = proj_dict.get("title") or "Sin título"
    
    click.secho(f"BioProject : {p_acc} | {p_title}", bold=True)
    
    s_acc = proj_dict.get("study_accession")
    gse = proj_dict.get("gse")
    links = proj_dict.get("links", {})
    
    if s_acc: 
        sra_url = f" -> {links['sra']}" if "sra" in links else ""
        click.echo(f"Study SRA  : {s_acc}{sra_url}")
        
    if gse:
        geo_url = f" -> {links['geo']}" if "geo" in links else ""
        click.echo(f"Serie GEO  : {gse}{geo_url}")
        
    if "bioproject" in links:
        click.echo(f"URL Base   : {links['bioproject']}")
        
    click.echo(f"Tipo       : {proj_dict.get('project_type', '-')}")
    
    p_abstract = proj_dict.get("abstract", "")
    if p_abstract:
        short_abs = p_abstract[:150] + "..." if len(p_abstract) > 150 else p_abstract
        click.echo(f"Resumen    : {short_abs}")
    
    if include_pubs:
        pubs = proj_dict.get("publications", [])
        if pubs:
            click.echo("Publicaciones:")
            for p in pubs:
                pmid = p.get("pubmed_id")
                if pmid:
                    click.echo(f"  • PMID: {pmid}")


def _render_experiments_table(experiments):
    """Renderiza una lista de experimentos en formato de tabla plana."""
    if not experiments:
        return
        
    click.echo("═" * 80)
    # Sin la columna MODEL y restaurando anchos base
    click.secho(f"{'EXPERIMENT':<14} {'PLATFORM':<12} {'STRATEGY':<12} {'TITLE'}", bold=True)
    for exp in experiments:
        e_acc = str(exp.get("experiment_accession") or "-")[:14]
        e_plat = str(exp.get("platform") or "-")[:12]
        e_strat = str(exp.get("library_strategy") or exp.get("strategy") or "-")[:12]
        
        # El título ya no se corta, se imprime completo
        e_title = str(exp.get("title") or "")
        
        click.echo(f"{e_acc:<14} {e_plat:<12} {e_strat:<12} {e_title}")


def _render_experiment_block(exp_dict):
    """Renderiza el bloque detallado de un Experimento (para la vista de experimentos)"""
    e_acc = exp_dict.get("experiment_accession")
    if not e_acc or e_acc == "no_experiment":
        click.secho(f"Experiment : Sin experimento asociado", dim=True)
        return
        
    e_plat = exp_dict.get("platform") or "-"
    e_title = exp_dict.get("title") or exp_dict.get("experiment_title") or exp_dict.get("name") or "Sin título"
    
    if "library_strategy" not in exp_dict and "strategy" not in exp_dict:
        click.secho(f"Experiment : {e_acc} | {e_title}", bold=True)
        click.echo(f"Plataforma : {e_plat}")
    else:
        e_model = exp_dict.get("instrument_model") or "-"
        e_strat = exp_dict.get("library_strategy") or exp_dict.get("strategy") or "-"
        e_source = exp_dict.get("library_source") or "-"
        
        click.secho(f"Experiment : {e_acc} | {e_title}", bold=True)
        click.echo(f"Plataforma : {e_plat} ({e_model})")
        click.echo(f"Estrategia : {e_strat} | Fuente: {e_source}")
        if exp_dict.get('gpl'): 
            click.echo(f"GPL        : {exp_dict.get('gpl')}")


def _render_single_sample(s):
    s_acc = s.get("sample_accession") or "MUESTRA_DESCONOCIDA"
    bs_acc = s.get("biosample_accession")
    org = s.get("organism") or "Organismo no especificado"
    tax_id = s.get("taxon_id")
    gsm = s.get("gsm")
    title = s.get("title")
    desc = s.get("description")
    
    header = f"Sample     : {s_acc} | {org}"
    if tax_id: 
        header += f" (TaxID: {tax_id})"
        
    click.secho(header, bold=True)
    
    if bs_acc: click.echo(f"BioSample  : {bs_acc}")
    if gsm: click.echo(f"Muestra GEO: {gsm}")
    if title: click.echo(f"Título     : {title}")
    if desc and desc != title: click.echo(f"Desc.      : {desc}")
    
    attributes = s.get("attributes", {})
    if attributes:
        click.echo("Atributos  :")
        for k, v in attributes.items():
            if str(v).lower() in ["missing", "not applicable", "not collected"]:
                click.secho(f"  • {k}: {v}", dim=True)
            else:
                click.echo(f"  • {k}: {v}")


def _render_single_run(r):
    r_acc = r.get("run_accession") or "RUN_DESCONOCIDO"
    click.secho(f"Run SRA    : {r_acc}", bold=True)
    
    pub = str(r.get("published_date") or "-")[:10]
    click.echo(f"Publicado  : {pub}")
    
    spots = r.get("total_spots") or 0
    bases = r.get("total_bases") or 0
    click.echo(f"Spots      : {spots:,}")
    click.echo(f"Bases      : {bases:,}")
    
    alias = r.get("alias")
    if alias: click.echo(f"Alias      : {alias}")


# =========================================
# Renderizadores Específicos por Nivel
# =========================================

def _print_bioproject(item):
    proj = item.get("bioproject") if "bioproject" in item else item
    _render_bioproject_block(proj, include_pubs=True)
    _render_experiments_table(item.get("experiments", []))


def _print_experiment(item):
    proj = item.get("bioproject", {})
    if proj:
        _render_bioproject_block(proj, include_pubs=True)
        click.echo("═" * 80)

    for idx, exp in enumerate(item.get("experiments", [])):
        if idx > 0: click.echo("═" * 80)
        
        _render_experiment_block(exp)
        
        samples = exp.get("samples", [])
        if samples:
            sample_list = []
            for s in samples:
                s_acc = s.get("sample_accession") or ""
                s_org = s.get("organism") or ""
                label = f"{s_acc} ({s_org})" if s_org else s_acc
                sample_list.append(label)
            click.echo(f"Samples    : {', '.join(sample_list)}")

        runs = exp.get("runs", [])
        if runs:
            click.echo("═" * 80)
            click.secho(f"{'RUN':<15} {'SPOTS':<15} {'BASES':<15} {'PUBLISHED'}", bold=True)
            for run in runs:
                r_acc = run.get("run_accession") or "-"
                spots = run.get("total_spots") or 0
                bases = run.get("total_bases") or 0
                pub = str(run.get("published_date") or "-")[:10]
                click.echo(f"{r_acc:<15} {spots:<15,} {bases:<15,} {pub}")


def _print_sample(item):
    proj = item.get("bioproject", {})
    if proj:
        _render_bioproject_block(proj, include_pubs=False)

    # Ahora renderizamos los experimentos ANTES de la muestra
    _render_experiments_table(item.get("experiments", []))
    
    click.echo("═" * 80)
    _render_single_sample(item)


def _print_run(item):
    proj = item.get("bioproject", {})
    if proj:
        _render_bioproject_block(proj, include_pubs=False)
    
    # Ahora renderizamos los experimentos ANTES del run
    _render_experiments_table(item.get("experiments", []))
    
    click.echo("═" * 80)
    _render_single_run(item)