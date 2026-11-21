import getpass
import hashlib
import json
import secrets
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pymysql
from email_validator import validate_email
from werkzeug.security import generate_password_hash

warnings.simplefilter("error", getpass.GetPassWarning)
evidencia = Path(sys.argv[1])
DB, USER = "facturaciones_spa_qa", "qa_facturaciones"
EMAIL_A, EMAIL_B = "qa.emisor@example.invalid", "qa.emisor2@example.invalid"
resultado = {"id": "QA-DATOS-003", "inicio": datetime.now().astimezone().isoformat(),
    "base": DB, "estado": "INICIADO", "commit_confirmado": False,
    "nota": "Fixtures insertados por SQL; no demuestra creacion mediante aplicacion"}
conexion = None
codigo = 1
hash_web = None
try:
    print("Solo QA: se agregaran 1 Emisor, 1 cliente, 2 solicitudes y catalogos.")
    print("No se modificaran las cuentas existentes, ni se enviara correo.")
    clave_bd = getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    resultado["fase"] = "verificacion_previa"
    conexion = pymysql.connect(host="127.0.0.1", port=3306, user=USER, password=clave_bd,
        database=DB, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=False, connect_timeout=10, read_timeout=15, write_timeout=15)
    del clave_bd
    esperadas = {
        "adjuntos_solicitud":0, "auditoria":0, "clientes":0, "correos_entrantes":0,
        "envios_correo":0, "estados_solicitud":0, "facturas":0, "origenes_solicitud":0,
        "recuperaciones_password":0, "registros_xml":0, "roles":3, "solicitudes":0, "usuarios":3,
    }
    with conexion.cursor() as cur:
        cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta")
        identidad=cur.fetchone()
        if identidad != {"bd":DB,"cuenta":USER+"@127.0.0.1"}:
            raise RuntimeError("CONEXION_NO_ES_QA")
        resultado["cuenta_bd_verificada"]=identidad["cuenta"]
        cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'",(DB,))
        if {r["TABLE_NAME"] for r in cur.fetchall()} != set(esperadas):
            raise RuntimeError("TABLAS_QA_NO_ESPERADAS")
        conteos={}
        for tabla in sorted(esperadas):
            cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`")
            conteos[tabla]=cur.fetchone()["total"]
        resultado["conteos_antes"]=conteos
        if conteos != esperadas:
            raise RuntimeError("DATOS_QA_NO_ESPERADOS_NO_SE_SOBRESCRIBE")
        cur.execute("SELECT id,nombre FROM roles")
        roles={r["nombre"]:r["id"] for r in cur.fetchall()}
        if set(roles)!={"Administrador","Emisor","Lector"}:
            raise RuntimeError("ROLES_NO_ESPERADOS")
        cur.execute("SELECT u.id,u.email,u.nombre,u.activo,u.debe_cambiar_password,u.ultimo_login,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id")
        usuarios=cur.fetchall()
        cuentas_esperadas={
            "qa.admin@example.invalid":("Administrador","Administrador Sintetico QA"),
            EMAIL_A:("Emisor","Emisor Sintetico QA"),
            "qa.lector@example.invalid":("Lector","Lector Sintetico QA"),
        }
        if {u["email"] for u in usuarios}!=set(cuentas_esperadas):
            raise RuntimeError("CUENTAS_NO_ESPERADAS")
        for u in usuarios:
            if (u["rol"],u["nombre"])!=cuentas_esperadas[u["email"]] or u["activo"]!=1 or u["debe_cambiar_password"]:
                raise RuntimeError("ESTADO_CUENTA_NO_ESPERADO")
        emisor_a=next(u for u in usuarios if u["email"]==EMAIL_A)
        resultado["usuarios_originales"]=usuarios

    contacto=validate_email("cliente.qa@example.com",check_deliverability=False,
        allow_smtputf8=False).normalized
    clave_web=getpass.getpass("Nueva clave WEB de qa.emisor2@example.invalid (12-128): ")
    repetir=getpass.getpass("Repite la clave WEB del segundo Emisor: ")
    if not 12<=len(clave_web)<=128 or clave_web!=repetir:
        raise RuntimeError("CLAVE_WEB_NO_VALIDA_O_NO_COINCIDE")
    hash_web=generate_password_hash(clave_web)
    del clave_web,repetir
    if input("Autorizar fixtures solo en QA. Escribe PREPARAR AISLAMIENTO QA: ").strip()!="PREPARAR AISLAMIENTO QA":
        raise RuntimeError("CANCELADO_POR_USUARIO")
    conexion.rollback()
    conexion.begin()
    resultado["fase"]="insercion_fixtures"
    with conexion.cursor() as cur:
        for tabla in sorted(esperadas):
            cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`")
            if cur.fetchone()["total"]!=esperadas[tabla]:
                raise RuntimeError("DATOS_CAMBIARON_DESDE_VERIFICACION")
        for nombre in ("Pendiente","En revisión","En corrección","Aprobada","Rechazada"):
            cur.execute(f"INSERT INTO `{DB}`.`estados_solicitud` (nombre) VALUES (%s)",(nombre,))
        for nombre in ("Web","Correo"):
            cur.execute(f"INSERT INTO `{DB}`.`origenes_solicitud` (nombre) VALUES (%s)",(nombre,))
        cur.execute(f"INSERT INTO `{DB}`.`usuarios` "
            "(rol_id,rut,nombre,email,password_hash,activo,debe_cambiar_password,password_actualizada_en) "
            "VALUES (%s,NULL,%s,%s,%s,1,0,UTC_TIMESTAMP())",
            (roles["Emisor"],"Segundo Emisor Sintetico QA",EMAIL_B,hash_web))
        id_b=cur.lastrowid
        hash_web=None
        cliente={"rut":"11111111-1","razon_social":"Cliente Sintetico QA Aislamiento",
            "direccion":"Direccion ficticia QA 123","giro":"Servicios de prueba QA","email_contacto":contacto}
        cur.execute(f"INSERT INTO `{DB}`.`clientes` "
            "(rut,razon_social,direccion,giro,email_contacto,activo) VALUES (%s,%s,%s,%s,%s,1)",
            (cliente["rut"],cliente["razon_social"],cliente["direccion"],cliente["giro"],contacto))
        id_cliente=cur.lastrowid
        cur.execute(f"SELECT id FROM `{DB}`.`estados_solicitud` WHERE nombre=%s",("Pendiente",))
        id_estado=cur.fetchone()["id"]
        cur.execute(f"SELECT id FROM `{DB}`.`origenes_solicitud` WHERE nombre=%s",("Web",))
        id_origen=cur.fetchone()["id"]
        marca=secrets.token_hex(4)
        fecha=datetime.now(timezone.utc).date().isoformat()
        columnas=("public_id","emisor_id","cliente_id","estado_id","origen_id","rut","nombre",
            "direccion","giro","email_contacto_receptor","concepto","nro_orden_compra",
            "fecha_emision","monto_bruto","tipo_afectacion","email_emisor","clave_idempotencia","huella_creacion")
        solicitudes=[]
        for etiqueta,id_emisor,email,monto in (("A",emisor_a["id"],EMAIL_A,"119000"),("B",id_b,EMAIL_B,"238000")):
            concepto="QA-HORIZONTAL-"+etiqueta+"-"+marca
            limpio={"cliente_id":id_cliente,"concepto":concepto,"monto_bruto":monto,
                "fecha_emision":fecha,"tipo_afectacion":"AFECTA","nro_orden_compra":None}
            huella=hashlib.sha256(json.dumps(limpio,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest()
            registro={"public_id":secrets.token_hex(16),"emisor_id":id_emisor,"cliente_id":id_cliente,
                "estado_id":id_estado,"origen_id":id_origen,"rut":cliente["rut"],"nombre":cliente["razon_social"],
                "direccion":cliente["direccion"],"giro":cliente["giro"],"email_contacto_receptor":contacto,
                "concepto":concepto,"nro_orden_compra":None,"fecha_emision":fecha,"monto_bruto":monto,
                "tipo_afectacion":"AFECTA","email_emisor":email,"clave_idempotencia":secrets.token_hex(16),
                "huella_creacion":huella}
            cols=", ".join("`"+c+"`" for c in columnas)
            valores=", ".join("%("+c+")s" for c in columnas)
            cur.execute(f"INSERT INTO `{DB}`.`solicitudes` ({cols}) VALUES ({valores})",registro)
            solicitudes.append({"etiqueta":etiqueta,"id":cur.lastrowid,"public_id":registro["public_id"],
                "emisor_id":id_emisor,"email_emisor":email,"concepto":concepto,
                "estado":"Pendiente","version":1,"monto_bruto":monto,"cliente_id":id_cliente})
        despues={}
        for tabla in sorted(esperadas):
            cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`")
            despues[tabla]=cur.fetchone()["total"]
        esperadas_despues=dict(esperadas,usuarios=4,clientes=1,solicitudes=2,estados_solicitud=5,origenes_solicitud=2)
        if despues!=esperadas_despues:
            raise RuntimeError("CONTEOS_FINALES_NO_ESPERADOS")
    conexion.commit()
    resultado["commit_confirmado"]=True
    resultado["estado"]="PREPARACION_CORRECTA"
    resultado["conteos_despues"]=despues
    resultado["usuarios_existentes_modificados"]=False
    resultado["solicitudes"]=solicitudes
    fixture={"id":"QA-DATOS-003","base":DB,"origen":"SQL de preparacion; no flujo funcional",
        "emisor_a":{"id":emisor_a["id"],"email":EMAIL_A,"nombre":"Emisor Sintetico QA"},
        "emisor_b":{"id":id_b,"email":EMAIL_B,"nombre":"Segundo Emisor Sintetico QA"},
        "cliente":dict(cliente,id=id_cliente),"solicitudes":solicitudes}
    (evidencia/"fixtures-aislamiento.json").write_text(json.dumps(fixture,ensure_ascii=True,indent=2),encoding="utf-8")
    print("PREPARACION CORRECTA: 4 usuarios, 1 cliente y 2 solicitudes, solo QA.")
    print("Conserva la clave WEB del segundo Emisor y la del Emisor original para Selenium.")
    codigo=0
except Exception as exc:
    if conexion is not None:
        conexion.rollback()
    resultado["estado"]="PREPARACION_NO_COMPLETADA"
    resultado["tipo_error"]=type(exc).__name__
    if isinstance(exc,RuntimeError):
        resultado["error_controlado"]=str(exc)
    elif isinstance(exc,pymysql.MySQLError) and exc.args and isinstance(exc.args[0],int):
        resultado["codigo_error_bd"]=exc.args[0]
    print("Preparacion detenida. Revisar resultado.json; no compartir claves ni hashes.")
finally:
    hash_web=None
    if conexion is not None:
        conexion.close()
    resultado["fin"]=datetime.now().astimezone().isoformat()
    (evidencia/"resultado.json").write_text(json.dumps(resultado,default=str,ensure_ascii=True,indent=2),encoding="utf-8")
raise SystemExit(codigo)