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

app = Flask(__name__)


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
