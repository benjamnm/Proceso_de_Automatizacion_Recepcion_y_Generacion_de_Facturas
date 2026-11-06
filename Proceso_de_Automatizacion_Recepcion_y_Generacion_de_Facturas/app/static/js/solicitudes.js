(() => {
    const selector = document.querySelector("#cliente_id");

    if (!selector) return;

    const campos = {
        rut: "preview-rut",
        razon: "preview-razon",
        giro: "preview-giro",
        direccion: "preview-direccion",
        correo: "preview-correo",
    };

    function actualizarCliente() {
        const opcion = selector.selectedOptions[0];

        Object.entries(campos).forEach(([dato, id]) => {
            const elemento = document.getElementById(id);

            if (elemento) {
                elemento.textContent = opcion?.dataset[dato] || "—";
            }
        });
    }

    selector.addEventListener("change", actualizarCliente);
    actualizarCliente();
})();