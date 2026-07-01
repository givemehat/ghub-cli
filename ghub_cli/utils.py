"""
Utilidades para esperar tareas asíncronas de Celery con una barra de
progreso en terminal.

El backend encola sync/sync-bulk/verify_otp como tareas de Celery y expone
su estado en GET /task/{task_id}. Como no sabemos de antemano cuánto va a
tardar una tarea, usamos una barra "spinner" (indeterminada) en vez de una
de progreso lineal con tiempo fijo — es más honesto sobre lo que sabemos.
"""
import itertools
import sys
import time

import click

from .client import GenomicHubClient, APIError

# Estados terminales que puede regresar Celery (vía /task/{task_id})
SUCCESS_STATES = {"success", "completed", "SUCCESS"}
FAILURE_STATES = {"error", "failed", "FAILURE"}
TERMINAL_STATES = SUCCESS_STATES | FAILURE_STATES

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def pretty_json(data) -> str:
    import json
    return json.dumps(data, indent=2, ensure_ascii=False)


def print_api_error(e: APIError) -> None:
    click.secho(f"✗ Error ({e.status_code}): {e.detail}", fg="red")
    if e.code:
        click.secho(f"  code: {e.code}", fg="red", dim=True)


def poll_task(
    client: GenomicHubClient,
    task_id: str,
    interval: float = 1.5,
    max_wait: int = 180,
    label: str = "Esperando tarea",
    show_result: bool = True,
    ask_to_continue: bool = True,
) -> dict | None:
    """
    Hace polling de /task/{task_id} con un spinner indeterminado hasta que
    la tarea llegue a un estado terminal (éxito o error).

    Si se agota max_wait sin llegar a un estado terminal, esto NO significa
    que la tarea haya fallado — Celery puede seguir corriendo perfectamente
    en el servidor. En ese caso:
      - si ask_to_continue=True (default), se pregunta al usuario si quiere
        seguir esperando otro ciclo de max_wait (útil en modo interactivo).
      - si ask_to_continue=False, simplemente se avisa y se regresa None,
        indicando cómo retomar la consulta más tarde.

    Regresa el último payload de /task/{task_id}, o None si hubo un error
    de API o el usuario decidió no seguir esperando (la tarea puede seguir
    corriendo en el servidor).
    """
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
                # Nuevo estado: limpiamos la línea y lo anunciamos
                click.echo()
                last_status = status

            frame = next(spinner)
            sys.stdout.write(
                f"\r{frame} {label}... [{status or '...'}] ({int(total_waited + waited)}s)"
            )
            sys.stdout.flush()

            if status in TERMINAL_STATES:
                sys.stdout.write("\n")
                sys.stdout.flush()
                if status in SUCCESS_STATES:
                    click.secho(f"✓ Tarea completada (task_id={task_id})", fg="green")
                else:
                    click.secho(f"✗ Tarea terminó con error (task_id={task_id})", fg="red")
                    if result.get("detail"):
                        click.secho(f"  detail: {result['detail']}", fg="red", dim=True)

                if show_result and result.get("data") is not None:
                    click.echo(pretty_json(result["data"]))

                return result

            time.sleep(interval)
            waited += interval

        total_waited += waited
        sys.stdout.write("\n")
        sys.stdout.flush()
        click.secho(
            f"⚠ Tiempo de espera agotado ({int(total_waited)}s). La tarea puede seguir "
            f"corriendo en el servidor.",
            fg="yellow",
        )

        if ask_to_continue and click.confirm("  ¿Seguir esperando?", default=True):
            continue

        click.secho(
            f"  Puedes consultarla más tarde con: ghub task {task_id} --poll",
            fg="yellow",
        )
        return None