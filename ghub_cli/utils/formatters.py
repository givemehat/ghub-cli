import json
import math
import click
from ghub_cli.core.client import APIError

def pretty_json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)

def format_size(size_bytes) -> str:
    """Formatea bytes al estilo de NCBI (binario: 1 MB/GB = 1024^n)."""
    if not size_bytes:
        return "-"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024

def print_api_error(e: APIError) -> None:
    click.secho(f"✗ Error ({e.status_code}): {e.detail}", fg="red")
    if e.code:
        click.secho(f"  code: {e.code}", fg="red", dim=True)

def _print_item_pagination(pagination):
    """Imprime el pie de paginación propio de un ítem (bioproject o experimento)."""
    if not pagination:
        return
    page = pagination.get("page", 1)
    page_size = pagination.get("page_size", 20)
    total_items = pagination.get("total_items", 0)
    paginas_totales = math.ceil(total_items / page_size) if page_size > 0 else 1
    
    click.echo("═" * 80)
    click.secho(f"Página {page} de {paginas_totales} ({page_size} items por página)", dim=True)

def print_formatted_search_results(data_list):
    if not data_list:
        click.secho("No se encontraron datos.", fg="yellow")
        return

    if isinstance(data_list, dict):
        data_list = data_list.get("data", [])

    if not data_list:
        click.secho("No se encontraron datos.", fg="yellow")
        return

    click.echo()

    for idx, item in enumerate(data_list):
        # Si ya pasamos el primer bloque, imprimimos un salto de línea limpio 
        # (por fuera de las líneas divisorias) para separarlo del siguiente.
        if idx > 0:
            click.echo() 
            
        click.echo("═" * 80) # Borde superior del bloque actual

        cli_type = item.get("_cli_type")
        
        # Respaldo por si no viene el tag (ej. consultas internas directas)
        if not cli_type:
            if "bioproject_accession" in item:
                cli_type = "bioproject"
            elif "experiments" in item:
                cli_type = "experiment"
            else:
                cli_type = "unknown"

        if cli_type == "bioproject":
            _print_bioproject(item)
        elif cli_type == "sample":
            _print_sample(item)
        elif cli_type == "run":
            _print_run(item)
        elif cli_type == "experiment":
            _print_experiment(item)
        else:
            click.secho("Ítem genérico", bold=True)
            click.echo(pretty_json(item))
            
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

    p_organism = proj_dict.get("organism")
    if p_organism:
        click.echo(f"Organismo  : {p_organism}")
    
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
    # Imprimimos la línea divisoria SIEMPRE, haya o no haya datos
    click.echo("═" * 80)
    
    if not experiments:
        return # Si está vacío, se sale aquí dejando la línea "hueca"
        
    click.secho(f"{'EXPERIMENT':<14} {'PLATFORM':<12} {'STRATEGY':<12} {'TITLE'}", bold=True)
    for exp in experiments:
        e_acc = str(exp.get("experiment_accession") or "-")[:14]
        e_plat = str(exp.get("platform") or "-")[:12]
        e_strat = str(exp.get("library_strategy") or exp.get("strategy") or "-")[:12]
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
    click.echo(f"Tamaño     : {format_size(r.get('size_bytes'))}")
    
    alias = r.get("alias")
    if alias: click.echo(f"Alias      : {alias}")


# =========================================
# Renderizadores Específicos por Nivel
# =========================================

def _print_bioproject(item):
    proj = item.get("bioproject") if "bioproject" in item else item
    _render_bioproject_block(proj, include_pubs=True)
    _render_experiments_table(item.get("experiments", []))
    
    pagination = item.get("pagination") or {
        "page": item.get("page", 1),
        "page_size": item.get("page_size", 20),
        "total_items": item.get("total_items", len(item.get("experiments", [])))
    }
    _print_item_pagination(pagination)


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
            click.secho(f"{'RUN':<15} {'SPOTS':<15} {'BASES':<15} {'SIZE':<12} {'PUBLISHED'}", bold=True)
            for run in runs:
                r_acc = run.get("run_accession") or "-"
                spots = run.get("total_spots") or 0
                bases = run.get("total_bases") or 0
                size = format_size(run.get("size_bytes"))
                pub = str(run.get("published_date") or "-")[:10]
                click.echo(f"{r_acc:<15} {spots:<15,} {bases:<15,} {size:<12} {pub}")
        else:
            # Línea para sellar visualmente el espacio vacío si no hay runs
            click.echo("═" * 80)

        _print_item_pagination(exp.get("pagination"))


def _print_sample(item):
    proj = item.get("bioproject", {})
    if proj:
        _render_bioproject_block(proj, include_pubs=False)

    experiments = item.get("experiments", [])
    _render_experiments_table(experiments)
    
    # Extraemos las muestras anidadas y eliminamos duplicados visuales
    seen_samples = set()
    for exp in experiments:
        for samp in exp.get("samples", []):
            s_acc = samp.get("sample_accession")
            if s_acc and s_acc not in seen_samples:
                click.echo("═" * 80)
                _render_single_sample(samp)
                seen_samples.add(s_acc)


def _print_run(item):
    proj = item.get("bioproject", {})
    if proj:
        _render_bioproject_block(proj, include_pubs=False)
    
    experiments = item.get("experiments", [])
    _render_experiments_table(experiments)
    
    # Extraemos los runs anidados
    seen_runs = set()
    for exp in experiments:
        for run in exp.get("runs", []):
            r_acc = run.get("run_accession")
            if r_acc and r_acc not in seen_runs:
                click.echo("═" * 80)
                _render_single_run(run)
                seen_runs.add(r_acc)
                

def print_formatted_explore_results(data_list, pagination=None):
    """Imprime los resultados del comando explore con el estilo visual de la CLI."""
    if not data_list:
        click.secho("No se encontraron resultados.", fg="yellow")
        return

    for idx, r in enumerate(data_list):
            
        click.echo("═" * 80)
        accession = r.get("bioproject_accession", "N/A")
        organism = r.get("organism") or "No especificado"
        title = r.get("title") or "Sin título"
        proj_type = r.get("project_type") or "-"
        
        click.secho(f"BioProject : {accession} | {title}", bold=True)
        click.echo(f"Organismo  : {organism}")
        click.echo(f"Tipo       : {proj_type}")
        
        if r.get("url"):
            click.echo(f"URL        : {r.get('url')}")
            
        click.echo("═" * 80)

    
    _print_item_pagination(pagination)
    click.echo("═" * 80)