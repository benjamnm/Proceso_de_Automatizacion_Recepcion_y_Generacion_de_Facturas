(() => {
    "use strict";

    const form = document.querySelector(".needs-validation");
    const passwordInput = document.querySelector("#password");
    const togglePassword = document.querySelector("#togglePassword");
    const passwordIcon = document.querySelector("#passwordIcon");

    form.addEventListener("submit", (event) => {
        if (!form.checkValidity()) {
            event.preventDefault();
            event.stopPropagation();
        }

        form.classList.add("was-validated");
    });

    togglePassword.addEventListener("click", () => {
        const shouldShow = passwordInput.type === "password";

        passwordInput.type = shouldShow
            ? "text"
            : "password";

        passwordIcon.classList.toggle(
            "bi-eye",
            !shouldShow
        );

        passwordIcon.classList.toggle(
            "bi-eye-slash",
            shouldShow
        );

        togglePassword.setAttribute(
            "aria-label",
            shouldShow
                ? "Ocultar contraseña"
                : "Mostrar contraseña"
        );
    });
})();