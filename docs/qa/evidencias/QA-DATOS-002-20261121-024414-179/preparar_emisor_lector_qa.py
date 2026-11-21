import getpass
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pymysql
from werkzeug.security import generate_password_hash

warnings.simplefilter("error", getpass.GetPassWarning)
evidencia = Path(sys.argv[1])
DB, USER = "facturaciones_spa_qa", "qa_facturaciones"
cuentas = [
    ("Emisor", "qa.emisor@example.invalid", "Emisor Sintetico QA"),
    ("Lector", "qa.lector@example.invalid", "Lector Sintetico QA"),
]
resultado = {"id": "QA-DATOS-002", "inicio": datetime.now().astimezone().isoformat(),
    "base": DB, "estado": "INICIADO", "commit_confirmado": False}
conexion = None
hashes = {}
codigo = 1
try:
    print("Solo se agregaran Emisor y Lector sinteticos a QA. El Administrador no se modifica.")
    clave_bd = getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    resultado["fase"] = "verificacion_previa"
    conexion = pymysql.connect(host="127.0.0.1", port=3306, user=USER,
        password=clave_bd, database=DB, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
        connect_timeout=10, read_timeout=15, write_timeout=15)
    del clave_bd
    with conexion.cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta")
        identidad = cursor.fetchone()
        if identidad != {"bd": DB, "cuenta": USER + "@127.0.0.1"}:
            raise RuntimeError("CONEXION_NO_ES_QA")
        resultado["cuenta_bd_verificada"] = identidad["cuenta"]
        cursor.execute("SELECT id,nombre FROM roles")
        roles = {r["nombre"]: r["id"] for r in cursor.fetchall()}
        if set(roles) != {"Administrador", "Emisor", "Lector"}:
            raise RuntimeError("ROLES_NO_ESPERADOS")
        cursor.execute("SELECT u.email,u.nombre,u.activo,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id")
        existentes = cursor.fetchall()
        if len(existentes) != 1 or existentes[0] != {
            "email": "qa.admin@example.invalid", "nombre": "Administrador Sintetico QA",
            "activo": 1, "rol": "Administrador"}:
            raise RuntimeError("USUARIOS_QA_NO_ESPERADOS_NO_SE_SOBRESCRIBE")
        resultado["usuarios_antes"] = existentes
        for tabla in ("clientes", "solicitudes"):
            cursor.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`")
            if cursor.fetchone()["total"] != 0:
                raise RuntimeError("HAY_DATOS_DE_NEGOCIO_REVISAR_ANTES")
    for rol, email, _ in cuentas:
        print("Elige una NUEVA clave WEB de 12-128 caracteres para " + email)
        clave = getpass.getpass("Clave WEB " + rol + ": ")
        confirmacion = getpass.getpass("Repite clave WEB " + rol + ": ")
        if not 12 <= len(clave) <= 128 or clave != confirmacion:
            raise RuntimeError("CLAVE_WEB_NO_VALIDA_O_NO_COINCIDE")
        hashes[email] = generate_password_hash(clave)
        del clave, confirmacion
    if input("Para crear solo estas dos cuentas escribe CREAR PERFILES QA: ").strip() != "CREAR PERFILES QA":
        raise RuntimeError("CANCELADO_POR_USUARIO")
    resultado["fase"] = "insercion_qa"
    conexion.rollback()
    conexion.begin()
    with conexion.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`usuarios`")
        if cursor.fetchone()["total"] != 1:
            raise RuntimeError("LOS_DATOS_CAMBIARON_DESDE_LA_VERIFICACION")
        for rol, email, nombre in cuentas:
            cursor.execute(
                f"INSERT INTO `{DB}`.`usuarios` "
                "(rol_id,rut,nombre,email,password_hash,activo,debe_cambiar_password,password_actualizada_en) "
                "VALUES (%s,NULL,%s,%s,%s,1,0,UTC_TIMESTAMP())",
                (roles[rol], nombre, email, hashes[email]),
            )
        cursor.execute("SELECT u.email,u.nombre,u.activo,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id ORDER BY u.email")
        resultado["usuarios_despues"] = cursor.fetchall()
        if len(resultado["usuarios_despues"]) != 3:
            raise RuntimeError("CANTIDAD_FINAL_NO_ESPERADA")
    conexion.commit()
    resultado["commit_confirmado"] = True
    resultado["usuarios_creados"] = 2
    resultado["usuarios_totales"] = 3
    resultado["administrador_modificado"] = False
    resultado["estado"] = "PREPARACION_CORRECTA"
    print("PREPARACION CORRECTA: Emisor y Lector creados; Administrador conservado.")
    print("Guarda las dos claves WEB de forma privada para el siguiente caso.")
    codigo = 0
except Exception as exc:
    if conexion is not None:
        conexion.rollback()
    resultado["estado"] = "PREPARACION_NO_COMPLETADA"
    resultado["tipo_error"] = type(exc).__name__
    if isinstance(exc, RuntimeError):
        resultado["error_controlado"] = str(exc)
    elif isinstance(exc, pymysql.MySQLError) and exc.args and isinstance(exc.args[0], int):
        resultado["codigo_error_bd"] = exc.args[0]
    print("Preparacion detenida; revisa resultado.json sin compartir claves ni hashes.")
finally:
    hashes.clear()
    if conexion is not None:
        conexion.close()
    resultado["fin"] = datetime.now().astimezone().isoformat()
    (evidencia / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=True, indent=2), encoding="utf-8")
raise SystemExit(codigo)