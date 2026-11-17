
// ========================================
// BÚSQUEDA Y FILTRADO DE SOLICITUDES
// ========================================

// obtiene los elementos HTML
const buscador = document.getElementById("buscar-solicitud");
const botonesFiltro = document.querySelectorAll(".filter-chip");
const filasSolicitudes = document.querySelectorAll(".requests-table tbody tr");

// estado seleccionado actualmente
let estadoActual = "all";

// función para filtrar las solicitudes
function filtrarSolicitudes() {

    // obtener el texto que escribió el usuario
    const textoBusqueda = buscador.value.toLowerCase().trim();

    // recorre todas las filas de la tabla
    filasSolicitudes.forEach(function (fila) {

        // obtener el contenido de la fila
        const contenidoFila = fila.textContent.toLowerCase();

        // obtener el estado de la solicitud
        const insigniaEstado = fila.querySelector(".status-badge");

        // comprobar si coincide con la búsqueda
        const coincideBusqueda = contenidoFila.includes(textoBusqueda);

        // comprobar si coincide con el filtro seleccionado
        const coincideEstado =
            estadoActual === "all" ||
            insigniaEstado.classList.contains("status-" + estadoActual);

        // mostrar u ocultar la fila
        if (coincideBusqueda && coincideEstado) {
            fila.style.display = "";
        } else {
            fila.style.display = "none";
        }

    });

}

// detectar cuando el usuario escribe en el buscador
buscador.addEventListener("input", filtrarSolicitudes);

// detectar cuando se selecciona un filtro
botonesFiltro.forEach(function (boton) {

    boton.addEventListener("click", function () {

        // actualizar el estado seleccionado
        estadoActual = boton.dataset.status;

        // quitar la clase activa de todos los botones
        botonesFiltro.forEach(function (elemento) {
            elemento.classList.remove("active");
        });

        // activar el botón seleccionado
        boton.classList.add("active");

        // aplicar los filtros
        filtrarSolicitudes();

    });

});
