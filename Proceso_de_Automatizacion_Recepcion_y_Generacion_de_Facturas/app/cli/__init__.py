import click

from ..services.correo import (
    ErrorCorreo,
    construir_mensaje,
    enviar,
    validar_configuracion,
)
from ..services.validaciones import ErrorValidacion, normalizar_correo


def registrar_comandos(app):
    @app.cli.command("smtp-prueba")
    @click.argument("destinatario")
    def smtp_prueba(destinatario):
        """Envía un correo de prueba para validar la configuración SMTP."""
        try:
            destinatario = normalizar_correo(destinatario)
        except ErrorValidacion as exc:
            raise click.ClickException(str(exc)) from exc

        try:
            cfg = validar_configuracion()
            mensaje = construir_mensaje(
                remitente=cfg["remitente"],
                remitente_correo=cfg["remitente_correo"],
                destinatario=destinatario,
                asunto="Prueba SMTP - Facturaciones SpA",
                cuerpo=(
                    "Correo de prueba de configuración SMTP.\n"
                    f"Servidor: {cfg['host']}:{cfg['puerto']} "
                    f"({cfg['seguridad']})\n"
                ),
            )
            message_id = enviar(mensaje, cfg)
        except ErrorCorreo as exc:
            raise click.ClickException(
                f"[{exc.codigo}] {exc} | {exc.detalle}"
            ) from exc

        click.echo(f"Correo enviado a {destinatario}. Message-ID: {message_id}")
