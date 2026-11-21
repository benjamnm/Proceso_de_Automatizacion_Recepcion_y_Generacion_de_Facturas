/*
 * Bandeja de correos: consulta una firma JSON cada N segundos y recarga si
 * cambió. Si el usuario está escribiendo solo avisa; se pausa con la
 * pestaña oculta. La recarga lleva ?auto=1 para no contar como actividad.
 */
(() => {
    "use strict";

    const raiz = document.querySelector("[data-auto-actualizar]");
    if (!raiz) {
        return;
    }

    const url = raiz.dataset.url;
    const intervalo = Math.max(10, Number(raiz.dataset.intervalo) || 20) * 1000;
    const interruptor = raiz.querySelector("[data-auto-actualizar-interruptor]");
    const estado = raiz.querySelector("[data-auto-actualizar-estado]");
    const aviso = document.querySelector("[data-auto-actualizar-aviso]");
    const CLAVE = "bandeja-auto-actualizar";

    let firma = raiz.dataset.firma;
    let temporizador = null;
    let hayNovedades = false;

    // Quita ?auto=1 de la barra para que un F5 manual sí cuente como actividad.
    const actual = new URL(window.location.href);
    if (actual.searchParams.has("auto")) {
        actual.searchParams.delete("auto");
        window.history.replaceState(null, "", actual.toString());
    }

    try {
        if (window.localStorage.getItem(CLAVE) === "0") {
            interruptor.checked = false;
        }
    } catch (e) { /* almacenamiento no disponible */ }

    const hora = () => new Date().toLocaleTimeString("es-CL");

    const usuarioEditando = () => {
        const activo = document.activeElement;
        if (activo && activo.matches("input:not([type=checkbox]), textarea, select")) {
            return true;
        }
        return Array.from(document.querySelectorAll("input[name=motivo]"))
            .some((campo) => campo.value.trim() !== "");
    };

    const recargar = (automatica = true) => {
        const destino = new URL(window.location.href);
        if (automatica) {
            destino.searchParams.set("auto", "1");
        }
        window.location.replace(destino.toString());
    };

    const mostrarAviso = () => {
        if (aviso) {
            aviso.classList.remove("d-none");
            aviso.classList.add("d-flex");
        }
    };

    const consultar = async () => {
        if (document.hidden || !interruptor.checked) {
            return;
        }
        try {
            const respuesta = await fetch(url, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
                cache: "no-store",
            });

            // Sesión vencida o sin permiso: recargar lleva al login.
            if (respuesta.redirected || respuesta.status === 401 || respuesta.status === 403) {
                window.location.reload();
                return;
            }
            if (!respuesta.ok) {
                estado.textContent = `Sin conexión con el servidor (${hora()}).`;
                return;
            }

            const datos = await respuesta.json();
            estado.textContent =
                `Por revisar: ${datos.por_revisar} · facturas por validar: ` +
                `${datos.por_validar} · consultado ${hora()}`;

            if (datos.firma && datos.firma !== firma) {
                hayNovedades = true;
                if (usuarioEditando()) {
                    mostrarAviso();
                } else {
                    recargar();
                }
            }
        } catch (e) {
            estado.textContent = `Sin conexión con el servidor (${hora()}).`;
        }
    };

    const programar = () => {
        window.clearInterval(temporizador);
        temporizador = null;
        if (interruptor.checked) {
            temporizador = window.setInterval(consultar, intervalo);
        } else {
            estado.textContent = "Actualización automática en pausa.";
        }
    };

    interruptor.addEventListener("change", () => {
        try {
            window.localStorage.setItem(CLAVE, interruptor.checked ? "1" : "0");
        } catch (e) { /* almacenamiento no disponible */ }
        programar();
        if (interruptor.checked) {
            consultar();
        }
    });

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            consultar();
        }
    });

    // Si había novedades y el usuario dejó de escribir, recarga.
    document.addEventListener("focusout", () => {
        window.setTimeout(() => {
            if (hayNovedades && interruptor.checked && !usuarioEditando()) {
                recargar();
            }
        }, 300);
    });

    aviso?.querySelector("[data-auto-actualizar-recargar]")
        ?.addEventListener("click", () => recargar(false));

    programar();
})();
