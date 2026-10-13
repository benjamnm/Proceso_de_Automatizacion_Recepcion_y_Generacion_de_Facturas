import re
from datetime import date
from decimal import Decimal
from email_validator import EmailNotValidError, validate_email


class ErrorValidacion(ValueError):
    pass


def normalizar_rut(valor):
    if not isinstance(valor, str):
        raise ErrorValidacion("Ingrese un RUT válido.")

    compacto = (
        valor.strip()
        .upper()
        .replace(".", "")
        .replace(" ", "")
    )

    if not re.fullmatch(r"[0-9]{1,8}-?[0-9K]", compacto):
        raise ErrorValidacion(
            "El RUT debe incluir el número y su dígito verificador."
        )

    sin_guion = compacto.replace("-", "")
    cuerpo = sin_guion[:-1]
    verificador = sin_guion[-1]

    numero = int(cuerpo)

    if numero == 0:
        raise ErrorValidacion("El RUT no puede ser igual a cero.")

    cuerpo = str(numero)

    suma = sum(
        int(digito) * (2 + posicion % 6)
        for posicion, digito in enumerate(reversed(cuerpo))
    )

    resultado = 11 - (suma % 11)

    if resultado == 11:
        esperado = "0"
    elif resultado == 10:
        esperado = "K"
    else:
        esperado = str(resultado)

    if verificador != esperado:
        raise ErrorValidacion(
            "El dígito verificador del RUT no es correcto."
        )

    return f"{cuerpo}-{verificador}"


def normalizar_correo(valor):
    try:
        resultado = validate_email(
            valor.strip(),
            check_deliverability=False,
            allow_smtputf8=False,
        )
    except EmailNotValidError as exc:
        raise ErrorValidacion(
            "Ingrese un correo electrónico válido."
        ) from exc

    correo = resultado.normalized

    if len(correo) > 150:
        raise ErrorValidacion(
            "El correo no puede superar 150 caracteres."
        )

    return correo


def validar_cliente(datos):
    limpio = {}
    errores = {}

    campos_texto = {
        "razon_social": ("La razón social", 150),
        "giro": ("El giro", 150),
        "direccion": ("La dirección", 200),
    }

    for campo, (etiqueta, limite) in campos_texto.items():
        valor = datos.get(campo, "").strip()

        if not valor:
            errores[campo] = f"{etiqueta} es obligatoria."
        elif len(valor) > limite:
            errores[campo] = (
                f"{etiqueta} no puede superar {limite} caracteres."
            )
        else:
            limpio[campo] = valor

    try:
        limpio["rut"] = normalizar_rut(datos.get("rut", ""))
    except ErrorValidacion as exc:
        errores["rut"] = str(exc)

    try:
        limpio["email_contacto"] = normalizar_correo(
            datos.get("email_contacto", "")
        )
    except ErrorValidacion as exc:
        errores["email_contacto"] = str(exc)

    return limpio, errores

def validar_solicitud(datos):
    limpio = {}
    errores = {}

    try:
        cliente_id = int(datos.get("cliente_id", ""))

        if cliente_id <= 0:
            raise ValueError

        limpio["cliente_id"] = cliente_id

    except (TypeError, ValueError):
        errores["cliente_id"] = "Seleccione un cliente válido."

    concepto = datos.get("concepto", "").strip()

    if not concepto:
        errores["concepto"] = "El concepto es obligatorio."
    elif len(concepto) > 500:
        errores["concepto"] = (
            "El concepto no puede superar 500 caracteres."
        )
    else:
        limpio["concepto"] = concepto

    orden = datos.get("nro_orden_compra", "").strip()

    if len(orden) > 40:
        errores["nro_orden_compra"] = (
            "La orden de compra no puede superar 40 caracteres."
        )
    else:
        limpio["nro_orden_compra"] = orden or None

    monto = datos.get("monto_bruto", "").strip()

    if not re.fullmatch(r"[0-9]{1,14}", monto):
        errores["monto_bruto"] = (
            "Ingrese un monto entero, sin puntos ni comas, "
            "de hasta 14 dígitos."
        )
    elif Decimal(monto) <= 0:
        errores["monto_bruto"] = "El monto debe ser mayor que cero."
    else:
        limpio["monto_bruto"] = Decimal(monto)

    fecha = datos.get("fecha_emision", "")

    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", fecha):
            raise ValueError

        fecha_validada = date.fromisoformat(fecha)

        if fecha_validada.year < 1000:
            raise ValueError

        limpio["fecha_emision"] = fecha_validada

    except (TypeError, ValueError):
        errores["fecha_emision"] = (
            "Ingrese una fecha válida entre los años 1000 y 9999."
        )

    afectacion = datos.get("tipo_afectacion", "")

    if afectacion not in {"AFECTA", "EXENTA"}:
        errores["tipo_afectacion"] = (
            "Seleccione una afectación válida."
        )
    else:
        limpio["tipo_afectacion"] = afectacion

    return limpio, errores