(() => {
    "use strict";

    document.addEventListener("submit", (event) => {
        const form = event.target;
        const mensaje = form.dataset.confirmar;

        if (mensaje && !window.confirm(mensaje)) {
            event.preventDefault();
            return;
        }

        if (form.hasAttribute("data-bloquear-envio")) {
            form.querySelectorAll("button[type='submit']").forEach((boton) => {
                boton.disabled = true;
            });
        }
    });
})();
