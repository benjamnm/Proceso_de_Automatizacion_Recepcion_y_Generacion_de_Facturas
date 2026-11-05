import re
from datetime import date
from decimal import Decimal

class ErrorValidacion(ValueError):
    """Error en un valor recibido por los filtros."""


def normalizar_rut(valor):
    """Valida el dígito verificador y devuelve el RUT sin puntos."""
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

CAMPOS_FILTRO = (
    "rut",
    "desde",
    "hasta",
    "monto",
    "estado_id",
    "emisor_id",
)


def construir_filtros_solicitud(
    argumentos,
    *,
    permitir_filtro_emisor=False,
):
    """
    Construye condiciones adicionales de búsqueda.

    No aplica autorización ni determina qué solicitudes puede ver
    un usuario. La consulta que utilice este resultado debe agregar
    obligatoriamente la condición de visibilidad correspondiente.

    Retorna:
        condiciones: lista de fragmentos SQL constantes.
        parametros: tupla de valores para la consulta parametrizada.
        filtros: valores recibidos, sin espacios en los extremos.
        errores: diccionario de mensajes por campo.
    """
    filtros = {}
    errores = {}
    condiciones = []
    parametros = []

    for campo in CAMPOS_FILTRO:
        valor = argumentos.get(campo, "")

        if valor is None:
            filtros[campo] = ""
        elif not isinstance(valor, str):
            filtros[campo] = ""
            errores[campo] = "El filtro debe ser un valor de texto."
        else:
            filtros[campo] = valor.strip()

    # RUT del receptor: coincidencia exacta normalizada.
    if filtros["rut"]:
        try:
            rut = normalizar_rut(filtros["rut"])
        except ErrorValidacion as exc:
            errores["rut"] = str(exc)
        else:
            condiciones.append("s.rut = %s")
            parametros.append(rut)

    # Fecha de emisión solicitada: rango inclusivo.
    fechas = {}

    for campo, operador in (("desde", ">="), ("hasta", "<=")):
        valor = filtros[campo]

        if not valor:
            continue

        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor):
                raise ValueError

            fechas[campo] = date.fromisoformat(valor)

        except ValueError:
            errores[campo] = (
                "Ingrese una fecha válida con formato AAAA-MM-DD."
            )
        else:
            condiciones.append(f"s.fecha_emision {operador} %s")
            parametros.append(fechas[campo])

    if (
        "desde" in fechas
        and "hasta" in fechas
        and fechas["desde"] > fechas["hasta"]
    ):
        errores["hasta"] = (
            "La fecha final no puede ser anterior a la fecha inicial."
        )

    # Monto bruto: coincidencia exacta.
    monto = filtros["monto"]

    if monto:
        if not re.fullmatch(r"[0-9]{1,14}", monto):
            errores["monto"] = (
                "Ingrese un monto entero de hasta 14 dígitos, "
                "sin puntos ni comas."
            )
        elif Decimal(monto) <= 0:
            errores["monto"] = "El monto debe ser mayor que cero."
        else:
            condiciones.append("s.monto_bruto = %s")
            parametros.append(Decimal(monto))

    # Estado y Emisor: identificadores positivos.
    for campo, columna in (
        ("estado_id", "s.estado_id"),
        ("emisor_id", "s.emisor_id"),
    ):
        valor = filtros[campo]

        if not valor:
            continue

        if campo == "emisor_id" and not permitir_filtro_emisor:
            errores[campo] = (
                "No tiene permiso para filtrar por Emisor."
            )
            continue

        if (
            not re.fullmatch(r"[0-9]{1,10}", valor)
            or not 1 <= int(valor) <= 4294967295
        ):
            errores[campo] = "Seleccione una opción válida."
            continue

        condiciones.append(f"{columna} = %s")
        parametros.append(int(valor))

    # Un filtro inválido no debe producir una búsqueda parcial.
    if errores:
        return [], (), filtros, errores

    return condiciones, tuple(parametros), filtros, errores