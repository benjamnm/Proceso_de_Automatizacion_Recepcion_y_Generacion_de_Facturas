
// ========================================
// CLIENTES DE DEMOSTRACIÓN
// ========================================

const selectorCliente = document.getElementById("cliente");
const campoRut = document.getElementById("rut-cliente");
const campoRazonSocial = document.getElementById("razon-social");
const campoCorreo = document.getElementById("correo-cliente");

const clientes = {
    "cliente-1": {
        rut: "76.482.115-3",
        razonSocial: "Constructora Los Andes Ltda.",
        correo: "contacto@losandes.cl"
    },

    "cliente-2": {
        rut: "77.019.884-K",
        razonSocial: "Clínica Dental Sonrisa SpA",
        correo: "administracion@sonrisa.cl"
    },

    "cliente-3": {
        rut: "78.330.442-1",
        razonSocial: "Transportes Ruta Sur Ltda.",
        correo: "contacto@rutasur.cl"
    },

    "cliente-4": {
        rut: "9.876.543-2",
        razonSocial: "Panadería La Espiga",
        correo: "contacto@laespiga.cl"
    }
};


// ========================================
// AUTOCOMPLETADO DEL CLIENTE
// ========================================

selectorCliente.addEventListener("change", function () {
    const clienteSeleccionado = selectorCliente.value;
    const informacionCliente = clientes[clienteSeleccionado];

    if (informacionCliente) {
        campoRut.value = informacionCliente.rut;
        campoRazonSocial.value = informacionCliente.razonSocial;
        campoCorreo.value = informacionCliente.correo;
    } else {
        campoRut.value = "";
        campoRazonSocial.value = "";
        campoCorreo.value = "";
    }
});


// ========================================
// CONTADOR DE CARACTERES DEL CONCEPTO
// ========================================

const campoConcepto = document.getElementById("concepto");
const contadorConcepto = document.getElementById("concept-count");

campoConcepto.addEventListener("input", function () {
    const cantidadCaracteres = campoConcepto.value.length;

    contadorConcepto.textContent = `${cantidadCaracteres} / 500`;
});


// ========================================
// VALIDACIÓN DEL FORMULARIO
// ========================================

const formularioSolicitud = document.getElementById("request-form");
const mensajeFormulario = document.getElementById("form-message");

const campoMontoBruto = document.getElementById("monto-bruto");
const campoFecha = document.getElementById("fecha-emision");
const selectorAfectacion = document.getElementById("tipo-afectacion");
const campoOrdenCompra = document.getElementById("orden-compra");

function mostrarMensaje(mensaje, tipo) {
    mensajeFormulario.textContent = mensaje;
    mensajeFormulario.className = `form-message ${tipo}`;
}

formularioSolicitud.addEventListener("submit", function (event) {
    event.preventDefault();

    // limpiar mensaje anterior
    mensajeFormulario.textContent = "";
    mensajeFormulario.className = "form-message";

    // validación cliente
    if (!selectorCliente.value || !clientes[selectorCliente.value]) {
        mostrarMensaje("Debes seleccionar un cliente registrado.", "error");
        selectorCliente.focus();
        return;
    }

    // validación concepto
    const concepto = campoConcepto.value.trim();

    if (!concepto) {
        mostrarMensaje("Debes ingresar el concepto de facturación.", "error");
        campoConcepto.focus();
        return;
    }

    if (concepto.length > 500) {
        mostrarMensaje("El concepto no puede superar los 500 caracteres.", "error");
        campoConcepto.focus();
        return;
    }

    // validación monto bruto
    const montoTexto = campoMontoBruto.value.trim();
    const monto = Number(montoTexto);

    if (
        montoTexto === "" ||
        !Number.isSafeInteger(monto) ||
        monto < 1 ||
        montoTexto.length > 14
    ) {
        mostrarMensaje(
            "El monto bruto debe ser un número entero mayor que cero y de máximo 14 dígitos.",
            "error"
        );
        campoMontoBruto.focus();
        return;
    }

    // validación fecha
    if (!campoFecha.value) {
        mostrarMensaje("Debes ingresar la fecha de emisión solicitada.", "error");
        campoFecha.focus();
        return;
    }

    // validación tipo de factura
    if (!["afecta", "exenta"].includes(selectorAfectacion.value)) {
        mostrarMensaje("Debes seleccionar si la factura es afecta o exenta.", "error");
        selectorAfectacion.focus();
        return;
    }

    // validación orden de compra
    if (campoOrdenCompra.value.length > 40) {
        mostrarMensaje("La orden de compra no puede superar los 40 caracteres.", "error");
        campoOrdenCompra.focus();
        return;
    }

    // confirmación de demostración
    mostrarMensaje(
        "¡Validación correcta! La solicitud está lista para registrarse.",
        "success"
    );
});
