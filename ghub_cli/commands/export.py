import csv
import sys
import click
import json
import zipfile
import io
import re
from ghub_cli.core.client import APIError
from ghub_cli.utils.formatters import print_api_error
from ghub_cli.utils.tasks import poll_task

def _parse_pubs(pubs):
    """Convierte la lista de publicaciones en una cadena con PMID y DOI."""
    if not pubs: return ""
    formatted_pubs = []
    for p in pubs:
        pmid = p.get("pubmed_id")
        doi = p.get("doi")
        parts = []
        if pmid: parts.append(f"PMID:{pmid}")
        if doi: parts.append(f"DOI:{doi}")
        if parts:
            formatted_pubs.append(" | ".join(parts))
    return " ;; ".join(formatted_pubs)

def _make_flat_row(bp, s=None, e=None, r=None):
    """
    Combina los diccionarios en un solo renglón plano.
    Como los nombres de las columnas ya son únicos y universales desde 
    su creación, solo se requiere fusionar los diccionarios.
    """
    row = {}
    if bp: row.update(bp)
    if s: row.update(s)
    if e: row.update(e)
    if r: row.update(r)
    return row

@click.command("export")
@click.argument("raw_ids", nargs=-1, required=True)
@click.option("--format", "out_format", type=click.Choice(["json", "csv"]), default="csv", show_default=True, help="Formato de salida")
@click.option("--out", "-o", default=None, help="Ruta del archivo de salida (Directorio o archivo)")
@click.option("--flat", "-f", is_flag=True, help="Si es CSV, combina toda la metadata en un solo archivo aplanado.")
@click.option("--strict", "-s", is_flag=True, help="Modo estricto: Omite registros huérfanos que no tengan Runs finales asociados.")
@click.pass_context
def export_metadata(ctx, raw_ids, out_format, out, flat, strict):
    """Exporta toda la rama de metadatos de múltiples IDs a JSON, a un ZIP con 4 CSVs o a un CSV plano."""
    client = ctx.obj["client"]
    
    joined_input = " ".join(raw_ids)
    cleaned_input = re.sub(r'[\[\],;]', ' ', joined_input)
    target_ids = list(dict.fromkeys(cleaned_input.split()))

    if not target_ids:
        click.secho("✗ No se detectaron IDs válidos.", fg="red")
        sys.exit(1)

    click.echo(f"Verificando {len(target_ids)} ID(s) para exportación...")
    
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
                    click.echo()
                    click.echo("⠋ Sincronizando proyectos faltantes...... [pending] (0s)")
                    click.echo("⠙ Sincronizando proyectos faltantes...... [success] (0s)")
            except APIError as sync_err:
                if sync_err.status_code == 404:
                    click.echo()
                    click.echo("⠋ Sincronizando proyectos faltantes...... [pending] (0s)")
                    click.echo("⠙ Sincronizando proyectos faltantes...... [success] (0s)")
                else:
                    raise sync_err
            
            final_check = client.check_bulk(missing)
            failed_ids = final_check.get("missing_ids", [])
            
            if failed_ids:
                click.echo()
                click.secho(f"✗ Fallo de sincronización: {', '.join([f.upper() for f in failed_ids])}", fg="yellow")
            
            click.echo()

        click.echo("Extrayendo árbol de metadatos...")
        result = client.export_full_branch_batch(target_ids)
        data = result.get("data")
        
        if not data:
            click.secho("✗ No se encontraron datos para exportar.", fg="red")
            sys.exit(1)

        if isinstance(data, dict):
            data = [data]

        default_name = target_ids[0] if len(target_ids) == 1 else f"export_{len(target_ids)}_items"

        if out_format == "json":
            output_file = out or f"{default_name}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            click.secho(f"✓ Exportación completada exitosamente: {output_file}", fg="green", bold=True)
            
        elif out_format == "csv":
            
            bioprojects, samples, experiments, runs = {}, {}, {}, {}
            flat_rows = []
            
            # Recolector dinámico de atributos de muestra
            dynamic_attr_keys = set()
            
            for item in data:
                proj = item.get("project") or {}
                bp_acc = proj.get("bioproject_accession", "")
                
                bp_row = {
                    "bioproject_accession": bp_acc,
                    "study_accession": proj.get("study_accession", ""),
                    "bioproject_title": proj.get("title", ""),
                    "project_type": proj.get("project_type", ""),
                    "organism": proj.get("organism", ""),
                    "bioproject_submission_date": proj.get("submission_date", ""),
                    "contact_name": proj.get("contact_name", ""),
                    "contact_email": proj.get("contact_email", ""),
                    "center_name": proj.get("center_name", ""),
                    "bioproject_abstract": proj.get("abstract", ""),
                    "bioproject_design_description": proj.get("design_description", ""),
                    "gse": proj.get("gse", ""),
                    "publications": _parse_pubs(proj.get("publications", []))
                }
                
                if bp_acc and bp_acc not in bioprojects:
                    bioprojects[bp_acc] = bp_row
                
                samps = item.get("samples", [])
                
                if not samps and not strict:
                    flat_rows.append(_make_flat_row(bp_row))

                for samp in samps:
                    s_acc = samp.get("sample_accession", "")
                    exps = samp.get("experiments", [])
                    
                    if strict:
                        has_runs = any(exp.get("runs") for exp in exps)
                        if not has_runs:
                            continue 
                            
                    s_row = {
                        "sample_accession": s_acc,
                        "bioproject_accession": bp_acc,
                        "biosample_accession": samp.get("biosample_accession", ""),
                        "organism": samp.get("organism", ""),
                        "taxon_id": samp.get("taxon_id", ""),
                        "sample_title": samp.get("title", ""),
                        "gsm": samp.get("gsm", ""),
                        "sample_description": samp.get("description", "")
                    }
                    
                    # Explotamos los atributos dinámicamente como columnas filtrables
                    for k, v in samp.get("attributes", {}).items():
                        clean_k = k.strip().replace(" ", "_")
                        attr_key = f"attr_{clean_k}"
                        s_row[attr_key] = v
                        dynamic_attr_keys.add(attr_key)
                    
                    if s_acc and s_acc not in samples:
                        samples[s_acc] = s_row
                    
                    if not exps and not strict:
                        flat_rows.append(_make_flat_row(bp_row, s_row))

                    for exp in exps:
                        e_acc = exp.get("experiment_accession", "")
                        rn = exp.get("runs", [])
                        
                        if strict and not rn:
                            continue
                            
                        e_row = {
                            "experiment_accession": e_acc,
                            "bioproject_accession": bp_acc,
                            "sample_accession": s_acc,
                            "experiment_title": exp.get("title", ""),
                            "platform": exp.get("platform", ""),
                            "instrument_model": exp.get("instrument_model", ""),
                            "library_strategy": exp.get("library_strategy", "") or exp.get("strategy", ""),
                            "library_source": exp.get("library_source", ""),
                            "library_selection": exp.get("library_selection", ""),
                            "library_layout": exp.get("library_layout", ""),
                            "library_name": exp.get("library_name", ""),
                            "experiment_design_description": exp.get("design_description", ""),
                            "protocol": exp.get("protocol", ""),
                            "gpl": exp.get("gpl", "")
                        }
                        
                        if e_acc and e_acc not in experiments:
                            experiments[e_acc] = e_row
                        
                        if not rn and not strict:
                            flat_rows.append(_make_flat_row(bp_row, s_row, e_row))

                        for run in rn:
                            r_acc = run.get("run_accession", "")
                            
                            r_row = {
                                "run_accession": r_acc,
                                "bioproject_accession": bp_acc,
                                "sample_accession": s_acc,      
                                "experiment_accession": e_acc,
                                "run_alias": run.get("alias", ""),
                                "run_published_date": run.get("published_date", ""),
                                "total_spots": run.get("total_spots", run.get("spots", "")),
                                "total_bases": run.get("total_bases", run.get("bases", "")),
                                "size_bytes": run.get("size_bytes", "")
                            }
                            
                            if r_acc and r_acc not in runs:
                                runs[r_acc] = r_row

                            flat_rows.append(_make_flat_row(bp_row, s_row, e_row, r_row))

            if flat:
                output_file = out or f"{default_name}_flat.csv"
                if not flat_rows:
                    click.secho("✗ No hay datos suficientes para generar el CSV plano con los filtros actuales.", fg="red")
                    return

                raw_keys = []
                for row in flat_rows:
                    for k in row.keys():
                        if k not in raw_keys:
                            raw_keys.append(k)

                base_preferred = [
                    "bioproject_accession",
                    "run_accession",
                    "sample_accession",
                    "experiment_accession",
                    "study_accession",
                    "biosample_accession",
                    "bioproject_title",
                    "project_type",
                    "organism",
                    "bioproject_submission_date",
                    "contact_name",
                    "contact_email",
                    "center_name",
                    "gse",
                    "publications",
                    "bioproject_abstract",
                    "bioproject_design_description",
                    "run_alias",
                    "run_published_date",
                    "total_spots",
                    "total_bases",
                    "size_bytes",
                    "taxon_id",
                    "sample_title",
                    "gsm",
                    "sample_description"
                ]
                
                # Insertamos los atributos dinámicos justo después de la info de muestra
                sorted_attrs = sorted(list(dynamic_attr_keys))
                
                exp_preferred = [
                    "experiment_title",
                    "platform",
                    "instrument_model",
                    "library_strategy",
                    "library_source",
                    "library_selection",
                    "library_layout",
                    "library_name",
                    "experiment_design_description",
                    "protocol",
                    "gpl"
                ]

                preferred_order = base_preferred + sorted_attrs + exp_preferred

                all_keys = [k for k in preferred_order if k in raw_keys]
                
                for k in raw_keys:
                    if k not in all_keys:
                        all_keys.append(k)

                with open(output_file, 'w', newline='', encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=all_keys)
                    writer.writeheader()
                    for row in flat_rows:
                        writer.writerow(row)

                click.secho(f"✓ Exportación plana completada: {output_file}", fg="green", bold=True)
            
            else:
                output_file = out or f"{default_name}.zip"
                
                bp_fields = [
                    "bioproject_accession", "study_accession", "bioproject_title", "project_type", 
                    "organism", "bioproject_submission_date", "contact_name", "contact_email", 
                    "center_name", "bioproject_abstract", "bioproject_design_description", "gse", "publications"
                ]
                
                samp_fields = [
                    "sample_accession", "bioproject_accession", "biosample_accession", "organism", 
                    "taxon_id", "sample_title", "gsm", "sample_description"
                ] + sorted(list(dynamic_attr_keys))
                
                exp_fields = [
                    "experiment_accession", "bioproject_accession", "sample_accession", "experiment_title", 
                    "platform", "instrument_model", "library_strategy", "library_source", "library_selection", 
                    "library_layout", "library_name", "experiment_design_description", "protocol", "gpl"
                ]
                
                run_fields = [
                    "run_accession", "bioproject_accession", "sample_accession", "experiment_accession", 
                    "run_alias", "run_published_date", "total_spots", "total_bases", "size_bytes"
                ]

                with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    def write_csv_to_zip(filename, data_dict, fieldnames):
                        if not data_dict: return
                        string_buf = io.StringIO()
                        writer = csv.DictWriter(string_buf, fieldnames=fieldnames, extrasaction='ignore')
                        writer.writeheader()
                        for row in data_dict.values():
                            writer.writerow(row)
                        zipf.writestr(filename, string_buf.getvalue())
                    
                    write_csv_to_zip("bioprojects.csv", bioprojects, bp_fields)
                    write_csv_to_zip("samples.csv", samples, samp_fields)
                    write_csv_to_zip("experiments.csv", experiments, exp_fields)
                    write_csv_to_zip("runs.csv", runs, run_fields)

                click.secho(f"✓ Exportación completada exitosamente. Archivo empaquetado en: {output_file}", fg="green", bold=True)
                click.echo("  (El .zip contiene metadatos normalizados en: bioprojects.csv, samples.csv, experiments.csv, runs.csv)")
            
    except APIError as e:
        print_api_error(e)
        sys.exit(1)