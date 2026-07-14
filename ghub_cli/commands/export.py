import csv
import sys
import click
import json
from ghub_cli.core.client import APIError
from ghub_cli.utils.formatters import print_api_error

@click.command("export")
@click.argument("target_id")
@click.option("--format", "-f", "out_format", type=click.Choice(["json", "csv"]), default="csv", show_default=True, help="Formato de salida")
@click.option("--out", "-o", default=None, help="Ruta del archivo de salida")
@click.pass_context
def export_metadata(ctx, target_id, out_format, out):
    """Exporta toda la rama de metadatos de un ID a CSV o JSON."""
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

        output_file = out or f"{target_id}_export.{out_format}"

        if out_format == "json":
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
        elif out_format == "csv":
            headers = [
                "bioproject_accession", "bioproject_title", "project_type",
                "sample_accession", "organism",
                "experiment_accession", "platform",
                "run_accession", "spots", "bases"
            ]
            
            with open(output_file, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                
                for item in data:
                    proj = item.get("project") or {}
                    bp_acc = proj.get("accession", proj.get("bioproject_accession", ""))
                    bp_title = proj.get("title", "")
                    bp_type = proj.get("project_type", "")
                    
                    samples = item.get("samples") or []
                    if not samples:
                        writer.writerow([bp_acc, bp_title, bp_type, "", "", "", "", "", "", ""])
                        continue
                        
                    for samp in samples:
                        s_acc = samp.get("accession", samp.get("sample_accession", ""))
                        s_org = samp.get("organism", "")
                        
                        experiments = samp.get("experiments") or []
                        if not experiments:
                            writer.writerow([bp_acc, bp_title, bp_type, s_acc, s_org, "", "", "", "", ""])
                            continue
                            
                        for exp in experiments:
                            e_acc = exp.get("experiment_accession", "")
                            e_plat = exp.get("platform", "")
                            
                            runs = exp.get("runs") or []
                            if not runs:
                                writer.writerow([bp_acc, bp_title, bp_type, s_acc, s_org, e_acc, e_plat, "", "", ""])
                                continue
                                
                            for run in runs:
                                writer.writerow([
                                    bp_acc, bp_title, bp_type, s_acc, s_org,
                                    e_acc, e_plat, run.get("run_accession", ""),
                                    run.get("spots", ""), run.get("bases", "")
                                ])

        click.secho(f"✓ Exportación completada exitosamente: {output_file}", fg="green", bold=True)
        
    except APIError as e:
        print_api_error(e)
        sys.exit(1)