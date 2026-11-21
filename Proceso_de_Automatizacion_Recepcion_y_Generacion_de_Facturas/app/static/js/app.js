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

    function seleccionar(elemento) {
        if (typeof elemento.select === "function") {
            elemento.select();
            return;
        }
        const rango = document.createRange();
        rango.selectNodeContents(elemento);
        const seleccion = window.getSelection();
        seleccion.removeAllRanges();
        seleccion.addRange(rango);
    }

    function avisarCopiado(boton) {
        const original = boton.innerHTML;
        boton.textContent = "Copiado";
        window.setTimeout(() => { boton.innerHTML = original; }, 1500);
    }

    document.addEventListener("click", (event) => {
        const imprimir = event.target.closest("[data-imprimir]");
        if (imprimir) {
            // Siempre se imprime el diseño, aunque esté abierta otra pestaña.
            const pestana = document.getElementById("pestana-diseno");
            if (pestana && window.bootstrap && !pestana.disabled) {
                window.bootstrap.Tab.getOrCreateInstance(pestana).show();
            }
            window.print();
            return;
        }

        const copiar = event.target.closest("[data-copiar]");
        if (!copiar) {
            return;
        }

        const origen = document.querySelector(copiar.dataset.copiar);
        if (!origen) {
            return;
        }

        const texto = "value" in origen ? origen.value : origen.textContent;

        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(texto).then(
                () => avisarCopiado(copiar),
                () => seleccionar(origen),
            );
        } else {
            // Sin HTTPS no hay portapapeles: se deja el texto seleccionado.
            seleccionar(origen);
        }
    });
})();
