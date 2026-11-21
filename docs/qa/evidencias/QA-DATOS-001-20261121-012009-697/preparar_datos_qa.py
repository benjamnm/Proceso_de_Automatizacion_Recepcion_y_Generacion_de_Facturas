import getpass
import json
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pymysql
from werkzeug.security import generate_password_hash, check_password_hash

warnings.simplefilter("error", getpass.GetPassWarning)
evidencia = Path(sys.argv[1])
DB = "facturaciones_spa_qa"
USER = "qa_facturaciones"
EMAIL = "qa.admin@example.invalid"
resultado = {
    "id": "QA-DATOS-001", "inicio": datetime.now().astimezone().isoformat(),
    "base": DB, "usuario_bd": USER, "administrador_qa": EMAIL,
    "estado": "INICIADO", "commit_confirmado": False,
}
conexion = None
codigo = 1
try:
    print("Preparacion exclusiva de QA. No se lee .env ni se ejecuta seed.py.")
    print("Primero se solicitara la clave MariaDB, NO la del Administrador de la web.")
    clave_bd = getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    resultado["fase"] = "conexion_y_verificacion"
    conexion = pymysql.connect(
        host="127.0.0.1", port=3306, user=USER, password=clave_bd,
        database=DB, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=False, connect_timeout=10, read_timeout=15, write_timeout=15,
    )
    del clave_bd
    with conexion.cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS bd, CURRENT_USER() AS cuenta")
        identidad = cursor.fetchone()
        if identidad["bd"] != DB or identidad["cuenta"] != USER + "@127.0.0.1":
            raise RuntimeError("IDENTIDAD_NO_ESPERADA")
        resultado["cuenta_autenticada"] = identidad["cuenta"]
        cursor.execute("SHOW GRANTS FOR CURRENT_USER()")
        for fila in cursor.fetchall():
            grant = str(next(iter(fila.values())))
            m = re.search(r"^GRANT (.*?) ON (.*?) TO ", grant, re.I)
            if m is None:
                raise RuntimeError("PERMISOS_NO_RECONOCIDOS")
            privilegios = {v.strip().upper() for v in m.group(1).split(",")}
            ambito = m.group(2).replace("`", "").replace(chr(92), "")
            if "WITH GRANT OPTION" in grant.upper():
                raise RuntimeError("PERMISOS_EXCESIVOS")
            if ambito == "*.*":
                if privilegios != {"USAGE"}:
                    raise RuntimeError("PERMISOS_GLOBALES_EXCESIVOS")
            elif ambito != DB + ".*" or not privilegios <= {"SELECT", "INSERT", "UPDATE"}:
                raise RuntimeError("PERMISOS_FUERA_DE_QA")
        resultado["permisos_restringidos_verificados"] = True
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'", (DB,),
        )
        tablas = {r["TABLE_NAME"] for r in cursor.fetchall()}
        esperadas = {
            "adjuntos_solicitud", "auditoria", "clientes", "correos_entrantes",
            "envios_correo", "estados_solicitud", "facturas", "origenes_solicitud",
            "recuperaciones_password", "registros_xml", "roles", "solicitudes", "usuarios",
        }
        if tablas != esperadas:
            raise RuntimeError("ESQUEMA_NO_ESPERADO")
        cursor.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='usuarios'", (DB,),
        )
        columnas = {r["COLUMN_NAME"] for r in cursor.fetchall()}
        if not {"debe_cambiar_password", "password_actualizada_en"} <= columnas:
            raise RuntimeError("FALTAN_COLUMNAS_PASSWORD")
        conteos = {}
        for tabla in sorted(esperadas):
            cursor.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`")
            conteos[tabla] = cursor.fetchone()["total"]
        resultado["conteos_antes"] = conteos
        if any(conteos.values()):
            raise RuntimeError("QA_NO_ESTA_VACIA_NO_SE_SOBRESCRIBE")
    print("Conexion a QA y permisos limitados verificados. Las 13 tablas estan vacias.")
    print("Se crearan 3 roles y qa.admin@example.invalid; no se crearan clientes ni solicitudes.")
    print("Ahora elige una NUEVA clave para el Administrador WEB de QA (12-128 caracteres).")
    clave_admin = getpass.getpass("Nueva clave del Administrador WEB de QA: ")
    repetir = getpass.getpass("Repite la clave WEB de QA: ")
    if not 12 <= len(clave_admin) <= 128 or clave_admin != repetir:
        raise RuntimeError("CLAVE_WEB_NO_VALIDA_O_NO_COINCIDE")
    if input("Para autorizar estas altas solo en QA escribe CREAR QA: ").strip() != "CREAR QA":
        raise RuntimeError("CANCELADO_POR_USUARIO")
    hash_admin = generate_password_hash(clave_admin)
    del clave_admin, repetir
    resultado["fase"] = "insercion_qa"
    conexion.rollback()
    conexion.begin()
    with conexion.cursor() as cursor:
        # Revalidar inmediatamente antes de las altas, sin sobreescribir.
        cursor.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`usuarios`")
        if cursor.fetchone()["total"] != 0:
            raise RuntimeError("QA_CAMBIO_DESDE_VERIFICACION")
        for nombre, descripcion in (
            ("Administrador", "Acceso completo - datos sinteticos QA"),
            ("Emisor", "Gestiona sus propias solicitudes - QA"),
            ("Lector", "Solo lectura - QA"),
        ):
            cursor.execute(
                f"INSERT INTO `{DB}`.`roles` (nombre, descripcion) VALUES (%s,%s)",
                (nombre, descripcion),
            )
        cursor.execute(f"SELECT id FROM `{DB}`.`roles` WHERE nombre=%s", ("Administrador",))
        rol = cursor.fetchone()["id"]
        cursor.execute(
            f"INSERT INTO `{DB}`.`usuarios` "
            "(rol_id,rut,nombre,email,password_hash,activo,debe_cambiar_password,password_actualizada_en) "
            "VALUES (%s,NULL,%s,%s,%s,1,0,UTC_TIMESTAMP())",
            (rol, "Administrador Sintetico QA", EMAIL, hash_admin),
        )
        id_admin = cursor.lastrowid
        cursor.execute(
            f"SELECT password_hash FROM `{DB}`.`usuarios` WHERE id=%s", (id_admin,),
        )
        if cursor.fetchone()["password_hash"] != hash_admin:
            raise RuntimeError("VERIFICACION_INSERCION_NO_COINCIDE")
        del hash_admin
    conexion.commit()
    resultado["commit_confirmado"] = True
    resultado["estado"] = "PREPARACION_CORRECTA"
    resultado["roles_creados"] = 3
    resultado["usuarios_creados"] = 1
    resultado["id_administrador"] = id_admin
    resultado["nota"] = "Solo roles y Administrador; otros catalogos siguen vacios. No es prueba de login."
    print("PREPARACION CORRECTA: 3 roles y 1 Administrador WEB de QA creados.")
    print("Conserva la clave WEB de forma privada para el proximo caso Selenium.")
    codigo = 0
except Exception as exc:
    if conexion is not None:
        conexion.rollback()
    resultado["estado"] = "PREPARACION_NO_COMPLETADA"
    if isinstance(exc, pymysql.MySQLError):
        resultado["tipo_error"] = type(exc).__name__
        resultado["codigo_error_bd"] = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
    elif isinstance(exc, (RuntimeError, getpass.GetPassWarning)):
        resultado["tipo_error"] = str(exc) if isinstance(exc, RuntimeError) else "ENTRADA_OCULTA_NO_DISPONIBLE"
    else:
        resultado["tipo_error"] = type(exc).__name__
    print("Preparacion detenida. Revisa resultado.json; no compartas claves ni hashes.")
finally:
    if conexion is not None:
        conexion.close()
    resultado["fin"] = datetime.now().astimezone().isoformat()
    (evidencia / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
raise SystemExit(codigo)