// Solo presentación: contador de caracteres del concepto.
// No valida ni bloquea nada; maxlength sigue siendo la validación real.
(() => {
    "use strict";
    const campo = document.querySelector("#concepto");
    const contador = document.querySelector("#contador-concepto");
    if (!campo || !contador) return;
    const max = campo.maxLength;
    const actualizar = () => { contador.textContent = `${campo.value.length} / ${max}`; };
    campo.addEventListener("input", actualizar);
    actualizar();
})();
