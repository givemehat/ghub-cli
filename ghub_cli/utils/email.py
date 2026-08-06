from __future__ import annotations

import click

from ghub_cli.core.client import APIError
from ghub_cli.core.config import load_config, save_config
from ghub_cli.utils.formatters import print_api_error

CONTACT_EMAIL = "leticiavega@icat.unam.mx"


def guardar_email(cfg: dict, email: str):
    cfg["email"] = email
    save_config(cfg)
    click.secho("  ✓ Correo guardado para futuras sesiones.", fg="green")


def validar_y_guardar_email(client, cfg: dict, email: str) -> bool:
    """
    Valida un correo nuevo contra la API (usando el pseudo-run '__check__')
    y lo guarda en config si es válido.

    Retorna True si el correo quedó guardado y listo para usarse,
    False si fue rechazado (ya se le mostró el mensaje al usuario).
    """
    click.echo("  Verificando acceso...")
    try:
        client.request_download("__check__", email)
        guardar_email(cfg, email)
        return True
    except APIError as e:
        if e.status_code == 400 and "denegado" in e.detail.lower():
            click.secho("\n  ✗ Este correo no está registrado.", fg="red", bold=True)
            click.secho(f"  Para solicitar acceso escribe a: {CONTACT_EMAIL}", fg="yellow")
            return False
        elif e.status_code == 404 or "no existe" in e.detail.lower():
            # __check__ no existe en BD pero el email sí pasó — guardamos igual
            guardar_email(cfg, email)
            return True
        else:
            print_api_error(e)
            return False


def resolve_email(client, email: str = None) -> str | None:
    """
    Resuelve el correo a usar para operaciones de descarga vía flags/comandos
    (no interactivo).

    - Si `email` viene dado (--email), se usa tal cual y NO se sobrescribe
      el correo ya guardado en config.
    - Si no viene, se usa el guardado en config.
    - Si no hay ninguno guardado, se pide uno, se valida contra la API y
      se guarda para futuras sesiones.

    Retorna el email a usar, o None si no se pudo resolver (ya se le
    mostró el motivo al usuario).
    """
    if email:
        return email

    cfg = load_config()
    saved = cfg.get("email")
    if saved:
        return saved

    click.secho("  No tienes un correo guardado.", fg="yellow")
    new_email = click.prompt("  Ingresa tu correo institucional")

    if validar_y_guardar_email(client, cfg, new_email):
        return new_email
    return None
