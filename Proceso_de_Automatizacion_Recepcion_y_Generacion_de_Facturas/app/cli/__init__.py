import click

from ..services.correo import (
    ErrorCorreo,
    construir_mensaje,
    enviar,
    validar_configuracion,
)
from ..services.correo_entrante import (
    ErrorCorreoEntrante,
    conectar,
    revisar_bandeja,
    validar_configuracion_imap,
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

    @app.cli.command("imap-prueba")
    def imap_prueba():
        """Valida la conexión IMAP cifrada y cuenta los no leídos."""
        try:
            cfg = validar_configuracion_imap()
            conexion = conectar(cfg)
        except ErrorCorreoEntrante as exc:
            raise click.ClickException(
                f"[{exc.codigo}] {exc} | {exc.detalle}"
            ) from exc

        try:
            _, datos = conexion.uid("SEARCH", None, "UNSEEN")
            no_leidos = len((datos[0] or b"").split())
        finally:
            try:
                conexion.logout()
            except Exception:
                pass

        click.echo(
            f"Conexión IMAP correcta: {cfg['host']}:{cfg['puerto']} "
            f"({cfg['seguridad']}), carpeta {cfg['buzon']}. "
            f"No leídos: {no_leidos}."
        )

    @app.cli.command("correo-revisar")
    @click.option(
        "--solo-procesar", is_flag=True,
        help="No conecta a IMAP; solo procesa correos ya descargados.",
    )
    def correo_revisar(solo_procesar):
        """Descarga correos de facturación y genera las facturas.

        Pensado para el Programador de tareas de Windows (cada 5 minutos).
        """
        try:
            resultado = revisar_bandeja(descargar=not solo_procesar)
        except ErrorCorreoEntrante as exc:
            raise click.ClickException(str(exc)) from exc

        if resultado["descarga"]:
            click.echo(f"Descarga: {resultado['descarga']}")
        if resultado["error_descarga"]:
            click.echo(f"Error IMAP: {resultado['error_descarga']}", err=True)
        click.echo(f"Proceso: {resultado['proceso']}")

        if resultado["error_descarga"]:
            raise SystemExit(1)
