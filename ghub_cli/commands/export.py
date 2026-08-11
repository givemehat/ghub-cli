import csv
import sys
import click
import json
import zipfile
import io
from ghub_cli.core.client import APIError
from ghub_cli.utils.formatters import print_api_error

@click.command("export")
@click.argument("target_id")
@click.option("--format", "-f", "out_format", type=click.Choice(["json", "csv"]), default="csv", show_default=True, help="Formato de salida")
@click.option("--out", "-o", default=None, help="Ruta del archivo de salida (Directorio o .zip)")
@click.pass_context
def export_metadata(ctx, target_id, out_format, out):
    """Exporta toda la rama de metadatos de un ID a JSON o a un ZIP con 4 CSVs."""
    client = ctx.obj["client"]
    click.echo(f"Extrayendo árbol de metadatos para {target_id}...")
    
    try:
        result = client.export_full_branch(target_id)
        data = result.get("data")
        
        if not data:
            click.secho("✗ No se encontraron datos para exportar.", fg="red")
            sys.exit(1)

        if isinstance(data, dict):
            data = [data]

        if out_format == "json":
            output_file = out or f"{target_id}_export.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            click.secho(f"✓ Exportación completada exitosamente: {output_file}", fg="green", bold=True)
            
        elif out_format == "csv":
            output_file = out or f"{target_id}_export.zip"
            
            bioprojects = {}
            samples = {}
            experiments = {}
            runs = {}
            
            for item in data:
                proj = item.get("project") or {}
                bp_acc = proj.get("accession", proj.get("bioproject_accession", ""))
                
                if bp_acc and bp_acc not in bioprojects:
                    bioprojects[bp_acc] = {
                        "bioproject_accession": bp_acc,
                        "title": proj.get("title", ""),
                        "project_type": proj.get("project_type", "")
                    }
                
                for samp in item.get("samples", []):
                    s_acc = samp.get("accession", samp.get("sample_accession", ""))
                    if s_acc and s_acc not in samples:
                        samples[s_acc] = {
                            "sample_accession": s_acc,
                            "bioproject_accession": bp_acc,
                            "organism": samp.get("organism", ""),
                            "taxon_id": samp.get("taxon_id", "")
                        }
                    
                    for exp in samp.get("experiments", []):
                        e_acc = exp.get("experiment_accession", "")
                        if e_acc and e_acc not in experiments:
                            experiments[e_acc] = {
                                "experiment_accession": e_acc,
                                "sample_accession": s_acc,
                                "bioproject_accession": bp_acc,
                                "platform": exp.get("platform", ""),
                                "strategy": exp.get("library_strategy", "") or exp.get("strategy", "")
                            }
                        
                        for run in exp.get("runs", []):
                            r_acc = run.get("run_accession", "")
                            if r_acc and r_acc not in runs:
                                runs[r_acc] = {
                                    "run_accession": r_acc,
                                    "experiment_accession": e_acc,
                                    "sample_accession": s_acc,
                                    "bioproject_accession": bp_acc,
                                    "spots": run.get("total_spots", run.get("spots", "")),
                                    "bases": run.get("total_bases", run.get("bases", ""))
                                }

            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                def write_csv_to_zip(filename, data_dict, fieldnames):
                    if not data_dict: return
                    string_buf = io.StringIO()
                    writer = csv.DictWriter(string_buf, fieldnames=fieldnames, extrasaction='ignore')
                    writer.writeheader()
                    for row in data_dict.values():
                        writer.writerow(row)
                    zipf.writestr(filename, string_buf.getvalue())
                
                write_csv_to_zip("bioprojects.csv", bioprojects, ["bioproject_accession", "title", "project_type"])
                write_csv_to_zip("samples.csv", samples, ["sample_accession", "bioproject_accession", "organism", "taxon_id"])
                write_csv_to_zip("experiments.csv", experiments, ["experiment_accession", "sample_accession", "bioproject_accession", "platform", "strategy"])
                write_csv_to_zip("runs.csv", runs, ["run_accession", "experiment_accession", "sample_accession", "bioproject_accession", "spots", "bases"])

            click.secho(f"✓ Exportación completada exitosamente. Archivo empaquetado en: {output_file}", fg="green", bold=True)
            click.echo("  (El .zip contiene: bioprojects.csv, samples.csv, experiments.csv, runs.csv)")
            
    except APIError as e:
        print_api_error(e)
        sys.exit(1)