"""
API del Sistema de Loterías.
"""
import sqlite3
import secrets
import hashlib
import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g

from motor_premios import procesar_resultado, reversar_resultado

DB_PATH = "loterias.db"

LOTERIAS_CATALOGO = [
    ("LOTTO ACTIVO", 38, 30, 0, None, None),
    ("LA GRANJITA", 38, 30, 0, None, None),
    ("SELVA PLUS", 38, 30, 0, None, None),
    ("GUACHARO ACTIVO", 77, 60, 0, "75", 120),
    ("GUACHARITO MILLONARIO", 102, 70, 5, "99", 140),
    ("CHANCE ANIMALITO", 38, 30, 0, None, None),
    ("LOTTOREY", 38, 30, 0, None, None),
    ("LOTTOINTERNACIONAL", 38, 30, 0, None, None),
    ("TERMINALITO", 100, 70, 0, None, None),
    ("ANIMALITOS LA RICACHONA", 38, 30, 0, None, None),
    ("TRIOACTIVO", 1000, 600, 0, None, None),
    ("TERMINAL TRIO ACTIVO", 100, 70, 5, None, None),
    ("TRIPLE LA RICACHONA", 1000, 600, 0, None, None),
    ("TERMINAL LA RICACHONA", 100, 70, 5, None, None),
    ("TRIPLETA LOTTO ACTIVO", 0, 50, 0, None, None),
    ("TRIPLETA LA GRANJITA", 0, 50, 0, None, None),
    ("TRIPLETA SELVA PLUS", 0, 50, 0, None, None),
    ("TRIPLETA GUACHARO", 0, 100, 0, None, None),
]


def inicializar_si_hace_falta():
    """
    Se asegura de que la base de datos exista y tenga las tablas y el
    catálogo cargado. Corre cada vez que arranca la aplicación, para
    no depender de que el archivo sobreviva entre reinicios del
    servidor (importante en planes gratuitos con disco temporal).
    """
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='loterias'")
    ya_existe = cur.fetchone() is not None

    if not ya_existe:
        with open("schema.sql") as f:
            con.executescript(f.read())
        cur.executemany(
            "INSERT INTO loterias (nombre, cantidad_numeros, pago_normal, pago_aproximacion, numero_comodin, pago_comodin) VALUES (?,?,?,?,?,?)",
            LOTERIAS_CATALOGO,
        )
        cur.execute("SELECT id FROM loterias WHERE nombre = 'LA GRANJITA'")
        loteria_id = cur.fetchone()[0]
        cur.execute("INSERT INTO sorteos (loteria_id, hora) VALUES (?, ?)", (loteria_id, "15:00"))
        con.commit()
        print(f"Base de datos inicializada con {len(LOTERIAS_CATALOGO)} loterías.")
    con.close()


app = Flask(__name__)
inicializar_si_hace_falta()


@app.after_request
def agregar_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.before_request
def manejar_preflight():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
        

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def cerrar_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


@app.get("/demo/sorteo_prueba")
def demo_sorteo_prueba():
    """
    Endpoint TEMPORAL: crea (o reutiliza) un sorteo de LA GRANJITA a
    las 23:59, para poder probar ventas sin importar la hora real.
    """
    db = get_db()
    existente = db.execute(
        "SELECT s.id FROM sorteos s JOIN loterias l ON l.id = s.loteria_id WHERE l.nombre = 'LA GRANJITA' AND s.hora = '23:59'"
    ).fetchone()
    if existente:
        return jsonify({"sorteo_id": existente["id"], "mensaje": "Ya existía, reutilizado"})

    loteria = db.execute("SELECT id FROM loterias WHERE nombre = 'LA GRANJITA'").fetchone()
    cur = db.execute("INSERT INTO sorteos (loteria_id, hora) VALUES (?, '23:59')", (loteria["id"],))
    db.commit()
    return jsonify({"sorteo_id": cur.lastrowid, "mensaje": "Sorteo de prueba creado (cierra a las 23:59)"})


@app.get("/demo/seed")
def demo_seed():
    """
    Endpoint TEMPORAL solo para pruebas: crea un banquero, una agencia
    y una caja de ejemplo si no existen todavía, con credenciales fijas
    para poder probar login/ventas sin tener el panel administrador
    conectado aún.
    """
    db = get_db()
    existente = db.execute("SELECT id FROM usuarios WHERE usuario = 'caja1demo'").fetchone()
    if existente:
        return jsonify({"mensaje": "Los datos de prueba ya existen", "usuario": "caja1demo"})

    clave_hash = hash_password("clave123")

    cur = db.execute(
        "INSERT INTO usuarios (nombre, usuario, password_hash, rol) VALUES (?,?,?,?)",
        ("Admin Demo", "admindemo", clave_hash, "agencia"),
    )
    usuario_admin_id = cur.lastrowid

    cur = db.execute(
        "INSERT INTO usuarios (nombre, usuario, password_hash, rol) VALUES (?,?,?,?)",
        ("Banquero Demo", "banquerodemo", clave_hash, "banquero"),
    )
    usuario_banquero_id = cur.lastrowid

    cur = db.execute(
        "INSERT INTO banqueros (usuario_id, comision_sistema_pct) VALUES (?, 15)",
        (usuario_banquero_id,),
    )
    banquero_id = cur.lastrowid

    cur = db.execute(
        "INSERT INTO agencias (banquero_id, usuario_admin_id, nombre, comision_pct) VALUES (?,?,?,?)",
        (banquero_id, usuario_admin_id, "AGENCIA DEMO", 8),
    )
    agencia_id = cur.lastrowid

    cur = db.execute(
        "INSERT INTO usuarios (nombre, usuario, password_hash, rol) VALUES (?,?,?,?)",
        ("Caja Demo", "caja1demo", clave_hash, "caja"),
    )
    usuario_caja_id = cur.lastrowid

    cur = db.execute(
        "INSERT INTO cajas (agencia_id, usuario_id, nombre_caja) VALUES (?,?,?)",
        (agencia_id, usuario_caja_id, "Caja 1"),
    )
    caja_id = cur.lastrowid

    db.commit()

    return jsonify({
        "mensaje": "Datos de prueba creados",
        "usuario_login": "caja1demo",
        "password": "clave123",
        "caja_id": caja_id,
        "agencia_id": agencia_id,
    })


@app.get("/")
def inicio():
    return jsonify({"mensaje": "Sistema de Loterías funcionando", "estado": "ok"})


@app.post("/login")
def login():
    data = request.get_json()
    usuario = data.get("usuario", "")
    password = data.get("password", "")

    db = get_db()
    row = db.execute(
        "SELECT id, nombre, rol, activo, password_hash FROM usuarios WHERE usuario = ?",
        (usuario,),
    ).fetchone()

    if row is None or row["password_hash"] != hash_password(password):
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
    if not row["activo"]:
        return jsonify({"error": "Este usuario está bloqueado"}), 403

    return jsonify({"usuario_id": row["id"], "nombre": row["nombre"], "rol": row["rol"]})


@app.get("/loterias")
def listar_loterias():
    db = get_db()
    rows = db.execute("SELECT * FROM loterias").fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/sorteos")
def listar_sorteos():
    loteria_id = request.args.get("loteria_id")
    db = get_db()
    if loteria_id:
        rows = db.execute("SELECT * FROM sorteos WHERE loteria_id = ? AND activo = 1", (loteria_id,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM sorteos WHERE activo = 1").fetchall()
    return jsonify([dict(r) for r in rows])


def _sorteo_esta_abierto(db, sorteo_id):
    sorteo = db.execute("SELECT hora, minutos_cierre_antes FROM sorteos WHERE id = ?", (sorteo_id,)).fetchone()
    if sorteo is None:
        return False
    ahora = datetime.now()
    hora_sorteo = datetime.strptime(sorteo["hora"], "%H:%M").replace(year=ahora.year, month=ahora.month, day=ahora.day)
    cierre = hora_sorteo - timedelta(minutes=sorteo["minutos_cierre_antes"])
    return ahora < cierre


@app.post("/ventas")
def crear_venta():
    data = request.get_json()
    caja_id = data["caja_id"]
    moneda = data["moneda"]
    jugadas = data["jugadas"]

    if not jugadas:
        return jsonify({"error": "El ticket no tiene jugadas"}), 400

    db = get_db()
    for j in jugadas:
        if not _sorteo_esta_abierto(db, j["sorteo_id"]):
            return jsonify({"error": f"El sorteo {j['sorteo_id']} ya cerró la venta"}), 409

    caja = db.execute("SELECT agencia_id FROM cajas WHERE id = ?", (caja_id,)).fetchone()
    if caja is None:
        return jsonify({"error": "Caja no encontrada"}), 404

    total = sum(j["monto"] for j in jugadas)
    numero_ticket = str(secrets.randbelow(900000000) + 100000000)
    serial = str(secrets.randbelow(900000000) + 100000000)
    vence_en = (datetime.now() + timedelta(days=3)).isoformat(timespec="seconds")

    cur = db.execute(
        "INSERT INTO tickets (agencia_id, caja_id, numero_ticket, serial, moneda, total, vence_en) VALUES (?,?,?,?,?,?,?)",
        (caja["agencia_id"], caja_id, numero_ticket, serial, moneda, total, vence_en),
    )
    ticket_id = cur.lastrowid

    for j in jugadas:
        db.execute(
            "INSERT INTO jugadas (ticket_id, sorteo_id, tipo_jugada, numero_jugado, monto) VALUES (?,?,?,?,?)",
            (ticket_id, j["sorteo_id"], j["tipo_jugada"], j["numero_jugado"], j["monto"]),
        )
    db.commit()

    return jsonify({"ticket_id": ticket_id, "numero_ticket": numero_ticket, "serial": serial, "total": total, "vence_en": vence_en}), 201


@app.get("/agencias/<int:agencia_id>/ventas")
def ventas_de_agencia(agencia_id):
    db = get_db()
    rows = db.execute(
        "SELECT numero_ticket, moneda, total, estado, vendido_en FROM tickets WHERE agencia_id = ? ORDER BY vendido_en DESC",
        (agencia_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/resultados")
def registrar_resultado():
    data = request.get_json()
    db = get_db()
    cur = db.execute(
        "INSERT INTO resultados (sorteo_id, fecha, numero_ganador) VALUES (?,?,?)",
        (data["sorteo_id"], data.get("fecha", datetime.now().strftime("%Y-%m-%d")), data["numero_ganador"]),
    )
    db.commit()
    return jsonify({"resultado_id": cur.lastrowid}), 201


@app.post("/resultados/<int:resultado_id>/procesar")
def procesar(resultado_id):
    db = get_db()
    try:
        resumen = procesar_resultado(db, resultado_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify(resumen)


@app.post("/resultados/<int:resultado_id>/reversar")
def reversar(resultado_id):
    db = get_db()
    try:
        reversar_resultado(db, resultado_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
