from __future__ import annotations

import itertools
import sys
import time
import click
from ghub_cli.core.client import GenomicHubClient, APIError
from ghub_cli.utils.formatters import pretty_json, print_api_error

SUCCESS_STATES = {"success", "completed", "SUCCESS"}
FAILURE_STATES = {"error", "failed", "FAILURE"}
TERMINAL_STATES = SUCCESS_STATES | FAILURE_STATES
_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def poll_task(
    client: GenomicHubClient,
    task_id: str,
    interval: float = 1.5,
    max_wait: int = 180,
    label: str = "Esperando tarea",
    show_result: bool = True,
    ask_to_continue: bool = True,
) -> dict | None:
    total_waited = 0.0

    while True:
        spinner = itertools.cycle(_SPINNER_FRAMES)
        waited = 0.0
        last_status = None

        while waited < max_wait:
            try:
                result = client.task_status(task_id)
            except APIError as e:
                click.echo()
                print_api_error(e)
                return None

            status = result.get("status")

            if status != last_status:
                click.echo()
                last_status = status

            frame = next(spinner)
            sys.stdout.write(f"\r{frame} {label}... [{status or '...'}] ({int(total_waited + waited)}s)")
            sys.stdout.flush()

            if status in TERMINAL_STATES:
                sys.stdout.write("\n")
                sys.stdout.flush()
                
                # Si hay error y debemos mostrarlo, lo mostramos de forma limpia sin revelar UUIDs técnicos
                if show_result:
                    if status in FAILURE_STATES:
                        click.secho(f"✗ La tarea falló.", fg="red")
                        if result.get("detail"):
                            click.secho(f"  detail: {result['detail']}", fg="red", dim=True)
                    if result.get("data") is not None:
                        click.echo(pretty_json(result["data"]))
                        
                return result

            time.sleep(interval)
            waited += interval

        total_waited += waited
        sys.stdout.write("\n")
        sys.stdout.flush()
        click.secho(
            f"⚠ Tiempo de espera agotado ({int(total_waited)}s).",
            fg="yellow",
        )
        return None