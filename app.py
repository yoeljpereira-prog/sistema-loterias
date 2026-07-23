"""
API del Sistema de Loterías (versión PostgreSQL).
"""
import secrets
import hashlib
import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g
import psycopg2
import psycopg2.extras

from motor_premios import procesar_resultado, reversar_resultado

DATABASE_URL = os.environ["DATABASE_URL"]

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
    Se asegura de que las tablas existan y el catálogo esté cargado.
    Corre cada vez que arranca la aplicación.
    """
    con = psycopg2.connect(DATABASE_URL)
    cur = con.cursor()
    cur.execute("SELECT to_regclass('public.loterias')")
    ya_existe = cur.fetchone()[0] is not None

    if not ya_existe:
        with open("schema.sql") as f:
            schema_sql = f.read()
        for sentencia in schema_sql.split(";"):
            sentencia = sentencia.strip()
            if sentencia:
                cur.execute(sentencia)

        cur.executemany(
            """INSERT INTO loterias (nombre, cantidad_numeros, pago_normal, pago_aproximacion, numero_comodin, pago_comodin)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            LOTERIAS_CATALOGO,
        )
        cur.execute("SELECT id FROM loterias WHERE nombre = 'LA GRANJITA'")
        loteria_id = cur.fetchone()[0]
        cur.execute("INSERT INTO sorteos (loteria_id, hora) VALUES (%s, %s)", (loteria_id, "15:00"))
        con.commit()
        print(f"Base de datos inicializada con {len(LOTERIAS_CATALOGO)} loterías.")
    cur.close()
    con.close()


app = Flask(__name__)
inicializar_si_hace_falta()


@app.after_request
def agregar_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.before_request
def manejar_preflight():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200


def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return g.db


@app.teardown_appcontext
def cerrar_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def uno(db, sql, params=()):
    """Atajo: ejecuta y devuelve una sola fila (o None)."""
    cur = db.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    return row


def todos(db, sql, params=()):
    """Atajo: ejecuta y devuelve todas las filas."""
    cur = db.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def ejecutar(db, sql, params=()):
    """Atajo: ejecuta un INSERT/UPDATE/DELETE y hace commit."""
    cur = db.cursor()
    cur.execute(sql, params)
    db.commit()
    return cur


@app.get("/banqueros/mi")
def mi_banquero():
    usuario_id = request.args.get("usuario_id")
    db = get_db()
    row = uno(db, "SELECT * FROM banqueros WHERE usuario_id = %s", (usuario_id,))
    if row is None:
        return jsonify({"error": "No se encontró un banquero para este usuario"}), 404
    return jsonify(dict(row))


@app.get("/banqueros/<int:banquero_id>/agencias")
def agencias_de_banquero(banquero_id):
    db = get_db()
    agencias = todos(
        db,
        """SELECT a.id, a.nombre, a.comision_pct, a.activa, a.monto_minimo_jugada, u.nombre AS admin_nombre
           FROM agencias a JOIN usuarios u ON u.id = a.usuario_admin_id
           WHERE a.banquero_id = %s ORDER BY a.id""",
        (banquero_id,),
    )
    resultado = []
    for ag in agencias:
        fila = uno(
            db,
            """SELECT COALESCE(SUM(t.total), 0) AS ventas,
                      COALESCE(SUM(j.premio) FILTER (WHERE j.estado = 'ganador'), 0) AS premios
               FROM tickets t LEFT JOIN jugadas j ON j.ticket_id = t.id
               WHERE t.agencia_id = %s""",
            (ag["id"],),
        )
        ventas = float(fila["ventas"])
        premios = float(fila["premios"])
        comision = ventas * float(ag["comision_pct"]) / 100
        resultado.append({
            "id": ag["id"], "nombre": ag["nombre"], "admin_nombre": ag["admin_nombre"],
            "comision_pct": float(ag["comision_pct"]), "activa": bool(ag["activa"]),
            "monto_minimo_jugada": float(ag["monto_minimo_jugada"] or 0),
            "ventas": ventas, "premios": premios, "comision": comision,
            "total": ventas - comision - premios,
        })
    return jsonify(resultado)


@app.post("/agencias")
def crear_agencia():
    data = request.get_json()
    db = get_db()
    clave_hash = hash_password(data["password"])
    cur = ejecutar(
        db,
        "INSERT INTO usuarios (nombre, usuario, password_hash, rol) VALUES (%s,%s,%s,'agencia') RETURNING id",
        (data["admin_nombre"], data["admin_usuario"], clave_hash),
    )
    usuario_admin_id = cur.fetchone()["id"]
    cur = ejecutar(
        db,
        "INSERT INTO agencias (banquero_id, usuario_admin_id, nombre, comision_pct) VALUES (%s,%s,%s,%s) RETURNING id",
        (data["banquero_id"], usuario_admin_id, data["nombre"], data["comision_pct"]),
    )
    return jsonify({"agencia_id": cur.fetchone()["id"]}), 201


@app.post("/agencias/<int:agencia_id>/actualizar")
def actualizar_agencia(agencia_id):
    data = request.get_json()
    db = get_db()
    campos = ["nombre = %s", "comision_pct = %s"]
    valores = [data["nombre"], data["comision_pct"]]
    if "monto_minimo_jugada" in data:
        campos.append("monto_minimo_jugada = %s")
        valores.append(data["monto_minimo_jugada"])
    valores.append(agencia_id)
    ejecutar(db, f"UPDATE agencias SET {', '.join(campos)} WHERE id = %s", tuple(valores))
    return jsonify({"ok": True})


@app.post("/agencias/<int:agencia_id>/activar")
def activar_agencia(agencia_id):
    db = get_db()
    ag = uno(db, "SELECT activa FROM agencias WHERE id = %s", (agencia_id,))
    if ag is None:
        return jsonify({"error": "Agencia no encontrada"}), 404
    nuevo = 0 if ag["activa"] else 1
    ejecutar(db, "UPDATE agencias SET activa = %s WHERE id = %s", (nuevo, agencia_id))
    return jsonify({"ok": True, "activa": bool(nuevo)})


@app.get("/banqueros")
def listar_banqueros():
    db = get_db()
    banqueros = todos(
        db,
        """SELECT b.id, b.comision_sistema_pct, b.afiliacion_pagada, b.activo, u.nombre
           FROM banqueros b JOIN usuarios u ON u.id = b.usuario_id ORDER BY b.id""",
    )
    resultado = []
    for b in banqueros:
        fila = uno(
            db,
            """SELECT COALESCE(SUM(t.total), 0) AS ventas
               FROM tickets t JOIN agencias a ON a.id = t.agencia_id
               WHERE a.banquero_id = %s""",
            (b["id"],),
        )
        num_agencias = uno(db, "SELECT COUNT(*) AS n FROM agencias WHERE banquero_id = %s", (b["id"],))
        resultado.append({
            "id": b["id"], "nombre": b["nombre"], "comision_sistema_pct": float(b["comision_sistema_pct"]),
            "afiliacion_pagada": float(b["afiliacion_pagada"] or 0), "activo": bool(b["activo"]),
            "ventas": float(fila["ventas"]), "agencias": num_agencias["n"],
        })
    return jsonify(resultado)


@app.post("/banqueros")
def crear_banquero():
    data = request.get_json()
    db = get_db()
    clave_hash = hash_password(data["password"])
    cur = ejecutar(
        db,
        "INSERT INTO usuarios (nombre, usuario, password_hash, rol) VALUES (%s,%s,%s,'banquero') RETURNING id",
        (data["nombre"], data["usuario"], clave_hash),
    )
    usuario_id = cur.fetchone()["id"]
    cur = ejecutar(
        db,
        "INSERT INTO banqueros (usuario_id, comision_sistema_pct, afiliacion_pagada) VALUES (%s,%s,%s) RETURNING id",
        (usuario_id, data["comision_sistema_pct"], data.get("afiliacion_pagada", 0)),
    )
    return jsonify({"banquero_id": cur.fetchone()["id"]}), 201


@app.post("/banqueros/<int:banquero_id>/actualizar")
def actualizar_banquero(banquero_id):
    data = request.get_json()
    db = get_db()
    ejecutar(db, "UPDATE banqueros SET comision_sistema_pct = %s WHERE id = %s", (data["comision_sistema_pct"], banquero_id))
    return jsonify({"ok": True})


@app.post("/banqueros/<int:banquero_id>/activar")
def activar_banquero(banquero_id):
    db = get_db()
    b = uno(db, "SELECT activo FROM banqueros WHERE id = %s", (banquero_id,))
    if b is None:
        return jsonify({"error": "Banquero no encontrado"}), 404
    nuevo = 0 if b["activo"] else 1
    ejecutar(db, "UPDATE banqueros SET activo = %s WHERE id = %s", (nuevo, banquero_id))
    return jsonify({"ok": True, "activo": bool(nuevo)})


@app.get("/master/agencias")
def todas_las_agencias():
    db = get_db()
    rows = todos(
        db,
        """SELECT a.id, a.nombre, a.activa, a.servicio_resultados_activo, a.quien_carga_resultados,
                  a.comision_resultados_pct, u.nombre AS banquero_nombre
           FROM agencias a
           JOIN banqueros b ON b.id = a.banquero_id
           JOIN usuarios u ON u.id = b.usuario_id
           ORDER BY a.id""",
    )
    resultado = []
    for r in rows:
        fila = uno(db, "SELECT COALESCE(SUM(total), 0) AS ventas FROM tickets WHERE agencia_id = %s", (r["id"],))
        d = dict(r)
        d["ventas"] = float(fila["ventas"])
        resultado.append(d)
    return jsonify(resultado)


@app.post("/agencias/<int:agencia_id>/servicio")
def actualizar_servicio_resultados(agencia_id):
    data = request.get_json()
    db = get_db()
    campos = []
    valores = []
    for campo in ("servicio_resultados_activo", "quien_carga_resultados", "comision_resultados_pct"):
        if campo in data:
            campos.append(f"{campo} = %s")
            valores.append(data[campo])
    if not campos:
        return jsonify({"error": "Nada que actualizar"}), 400
    valores.append(agencia_id)
    ejecutar(db, f"UPDATE agencias SET {', '.join(campos)} WHERE id = %s", tuple(valores))
    return jsonify({"ok": True})


@app.get("/agencias/mi")
def mi_agencia():
    usuario_id = request.args.get("usuario_id")
    db = get_db()
    row = uno(db, "SELECT * FROM agencias WHERE usuario_admin_id = %s", (usuario_id,))
    if row is None:
        return jsonify({"error": "No se encontró una agencia para este usuario"}), 404
    return jsonify(dict(row))


@app.get("/agencias/<int:agencia_id>")
def info_agencia(agencia_id):
    db = get_db()
    row = uno(db, "SELECT * FROM agencias WHERE id = %s", (agencia_id,))
    if row is None:
        return jsonify({"error": "Agencia no encontrada"}), 404
    return jsonify(dict(row))


@app.post("/cajas")
def crear_caja():
    data = request.get_json()
    db = get_db()
    clave_hash = hash_password(data["password"])
    cur = ejecutar(
        db,
        "INSERT INTO usuarios (nombre, usuario, password_hash, rol) VALUES (%s,%s,%s,'caja') RETURNING id",
        (data["nombre"], data["usuario"], clave_hash),
    )
    usuario_id = cur.fetchone()["id"]
    cur = ejecutar(
        db,
        "INSERT INTO cajas (agencia_id, usuario_id, nombre_caja) VALUES (%s,%s,%s) RETURNING id",
        (data["agencia_id"], usuario_id, data["nombre_caja"]),
    )
    return jsonify({"caja_id": cur.fetchone()["id"]}), 201


@app.get("/agencias/<int:agencia_id>/cajas")
def listar_cajas(agencia_id):
    db = get_db()
    rows = todos(
        db,
        """SELECT c.id AS caja_id, c.nombre_caja, c.activo, u.nombre, u.usuario
           FROM cajas c JOIN usuarios u ON u.id = c.usuario_id
           WHERE c.agencia_id = %s ORDER BY c.id""",
        (agencia_id,),
    )
    return jsonify([dict(r) for r in rows])


@app.post("/cajas/<int:caja_id>/activar")
def activar_caja(caja_id):
    db = get_db()
    caja = uno(db, "SELECT activo FROM cajas WHERE id = %s", (caja_id,))
    if caja is None:
        return jsonify({"error": "Caja no encontrada"}), 404
    nuevo_estado = 0 if caja["activo"] else 1
    ejecutar(db, "UPDATE cajas SET activo = %s WHERE id = %s", (nuevo_estado, caja_id))
    return jsonify({"ok": True, "activo": bool(nuevo_estado)})


@app.get("/agencias/<int:agencia_id>/reporte-cajas")
def reporte_cajas(agencia_id):
    db = get_db()
    cajas = todos(
        db,
        """SELECT c.id AS caja_id, c.nombre_caja, u.nombre
           FROM cajas c JOIN usuarios u ON u.id = c.usuario_id
           WHERE c.agencia_id = %s""",
        (agencia_id,),
    )
    resultado = []
    for c in cajas:
        fila = uno(
            db,
            """SELECT
                 COALESCE(SUM(t.total), 0) AS ventas,
                 COALESCE(SUM(j.premio) FILTER (WHERE j.estado = 'ganador'), 0) AS premios,
                 COALESCE(SUM(j.premio) FILTER (WHERE j.premio_pagado = 1), 0) AS premios_pagados
               FROM tickets t
               LEFT JOIN jugadas j ON j.ticket_id = t.id
               WHERE t.caja_id = %s""",
            (c["caja_id"],),
        )
        ventas = float(fila["ventas"])
        premios = float(fila["premios"])
        premios_pagados = float(fila["premios_pagados"])
        resultado.append({
            "caja_id": c["caja_id"],
            "nombre_caja": c["nombre_caja"],
            "nombre": c["nombre"],
            "ventas": ventas,
            "premios": premios,
            "premios_pagados": premios_pagados,
            "premios_por_pagar": premios - premios_pagados,
            "total": ventas - premios_pagados,
        })
    return jsonify(resultado)


@app.get("/demo/sorteo_prueba")
def demo_sorteo_prueba():
    db = get_db()
    existente = uno(
        db,
        "SELECT s.id FROM sorteos s JOIN loterias l ON l.id = s.loteria_id WHERE l.nombre = 'LA GRANJITA' AND s.hora = '23:59'",
    )
    if existente:
        return jsonify({"sorteo_id": existente["id"], "mensaje": "Ya existía, reutilizado"})

    loteria = uno(db, "SELECT id FROM loterias WHERE nombre = 'LA GRANJITA'")
    fila = ejecutar(db, "INSERT INTO sorteos (loteria_id, hora) VALUES (%s, '23:59') RETURNING id", (loteria["id"],))
    nuevo_id = fila.fetchone()["id"]
    return jsonify({"sorteo_id": nuevo_id, "mensaje": "Sorteo de prueba creado (cierra a las 23:59)"})


@app.get("/demo/seed")
def demo_seed():
    """
    Endpoint TEMPORAL solo para pruebas: crea un banquero, una agencia
    y una caja de ejemplo si no existen todavía.
    """
    db = get_db()
    existente = uno(db, "SELECT id FROM usuarios WHERE usuario = 'caja1demo'")
    if existente:
        return jsonify({"mensaje": "Los datos de prueba ya existen", "usuario": "caja1demo"})

    clave_hash = hash_password("clave123")

    cur = ejecutar(
        db,
        "INSERT INTO usuarios (nombre, usuario, password_hash, rol) VALUES (%s,%s,%s,%s) RETURNING id",
        ("Admin Demo", "admindemo", clave_hash, "agencia"),
    )
    usuario_admin_id = cur.fetchone()["id"]

    cur = ejecutar(
        db,
        "INSERT INTO usuarios (nombre, usuario, password_hash, rol) VALUES (%s,%s,%s,%s) RETURNING id",
        ("Banquero Demo", "banquerodemo", clave_hash, "banquero"),
    )
    usuario_banquero_id = cur.fetchone()["id"]

    cur = ejecutar(
        db,
        "INSERT INTO banqueros (usuario_id, comision_sistema_pct) VALUES (%s, 15) RETURNING id",
        (usuario_banquero_id,),
    )
    banquero_id = cur.fetchone()["id"]

    cur = ejecutar(
        db,
        "INSERT INTO agencias (banquero_id, usuario_admin_id, nombre, comision_pct) VALUES (%s,%s,%s,%s) RETURNING id",
        (banquero_id, usuario_admin_id, "AGENCIA DEMO", 8),
    )
    agencia_id = cur.fetchone()["id"]

    cur = ejecutar(
        db,
        "INSERT INTO usuarios (nombre, usuario, password_hash, rol) VALUES (%s,%s,%s,%s) RETURNING id",
        ("Caja Demo", "caja1demo", clave_hash, "caja"),
    )
    usuario_caja_id = cur.fetchone()["id"]

    cur = ejecutar(
        db,
        "INSERT INTO cajas (agencia_id, usuario_id, nombre_caja) VALUES (%s,%s,%s) RETURNING id",
        (agencia_id, usuario_caja_id, "Caja 1"),
    )
    caja_id = cur.fetchone()["id"]

    return jsonify({
        "mensaje": "Datos de prueba creados",
        "usuario_login": "caja1demo",
        "password": "clave123",
        "caja_id": caja_id,
        "agencia_id": agencia_id,
    })


@app.post("/bloqueos")
def crear_bloqueo():
    data = request.get_json()
    db = get_db()
    cur = ejecutar(
        db,
        """INSERT INTO bloqueos_limites (nivel, nivel_id, loteria_id, sorteo_id, numero, tipo, monto_limite)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (
            data["nivel"], data["nivel_id"], data["loteria_id"], data.get("sorteo_id"),
            data["numero"], data["tipo"], data.get("monto_limite"),
        ),
    )
    return jsonify({"bloqueo_id": cur.fetchone()["id"]}), 201


@app.get("/bloqueos")
def listar_bloqueos():
    nivel = request.args.get("nivel")
    nivel_id = request.args.get("nivel_id")
    db = get_db()
    rows = todos(db, "SELECT * FROM bloqueos_limites WHERE nivel = %s AND nivel_id = %s", (nivel, nivel_id))
    return jsonify([dict(r) for r in rows])


@app.delete("/bloqueos/<int:bloqueo_id>")
def quitar_bloqueo(bloqueo_id):
    db = get_db()
    ejecutar(db, "DELETE FROM bloqueos_limites WHERE id = %s", (bloqueo_id,))
    return jsonify({"ok": True})


def _validar_bloqueos_y_limites(db, agencia_id, sorteo_id, numero_jugado, monto):
    sorteo = uno(db, "SELECT loteria_id FROM sorteos WHERE id = %s", (sorteo_id,))
    if sorteo is None:
        return "Sorteo no encontrado"
    loteria_id = sorteo["loteria_id"]

    agencia = uno(db, "SELECT banquero_id FROM agencias WHERE id = %s", (agencia_id,))
    banquero_id = agencia["banquero_id"] if agencia else None

    reglas = todos(
        db,
        """SELECT tipo, monto_limite FROM bloqueos_limites
           WHERE numero = %s AND loteria_id = %s AND (sorteo_id = %s OR sorteo_id IS NULL)
           AND ((nivel = 'agencia' AND nivel_id = %s) OR (nivel = 'banquero' AND nivel_id = %s))""",
        (numero_jugado, loteria_id, sorteo_id, agencia_id, banquero_id),
    )

    for regla in reglas:
        if regla["tipo"] == "bloqueado":
            return f"El número {numero_jugado} está bloqueado para este sorteo"
        if regla["tipo"] == "limite":
            fila = uno(
                db,
                "SELECT COALESCE(SUM(monto), 0) AS total FROM jugadas WHERE sorteo_id = %s AND numero_jugado = %s",
                (sorteo_id, numero_jugado),
            )
            ya_vendido = fila["total"]
            if ya_vendido + monto > regla["monto_limite"]:
                disponible = max(regla["monto_limite"] - ya_vendido, 0)
                return f"El número {numero_jugado} solo admite {disponible} más en este sorteo (límite {regla['monto_limite']})"
    return None


@app.get("/")
def inicio():
    return jsonify({"mensaje": "Sistema de Loterías funcionando", "estado": "ok"})


@app.post("/login")
def login():
    data = request.get_json()
    usuario = data.get("usuario", "")
    password = data.get("password", "")

    db = get_db()
    row = uno(db, "SELECT id, nombre, rol, activo, password_hash FROM usuarios WHERE usuario = %s", (usuario,))

    if row is None or row["password_hash"] != hash_password(password):
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
    if not row["activo"]:
        return jsonify({"error": "Este usuario está bloqueado"}), 403

    return jsonify({"usuario_id": row["id"], "nombre": row["nombre"], "rol": row["rol"]})


@app.get("/cajas/mi")
def mi_caja():
    usuario_id = request.args.get("usuario_id")
    db = get_db()
    row = uno(
        db,
        """SELECT c.id AS caja_id, c.nombre_caja, c.agencia_id, a.nombre AS agencia_nombre
           FROM cajas c JOIN agencias a ON a.id = c.agencia_id
           WHERE c.usuario_id = %s""",
        (usuario_id,),
    )
    if row is None:
        return jsonify({"error": "No se encontró una caja para este usuario"}), 404
    return jsonify(dict(row))


@app.get("/loterias")
def listar_loterias():
    db = get_db()
    rows = todos(db, "SELECT * FROM loterias")
    return jsonify([dict(r) for r in rows])


@app.get("/sorteos")
def listar_sorteos():
    loteria_id = request.args.get("loteria_id")
    db = get_db()
    if loteria_id:
        rows = todos(db, "SELECT * FROM sorteos WHERE loteria_id = %s AND activo = 1", (loteria_id,))
    else:
        rows = todos(db, "SELECT * FROM sorteos WHERE activo = 1")
    return jsonify([dict(r) for r in rows])


def _sorteo_esta_abierto(db, sorteo_id):
    sorteo = uno(db, "SELECT hora, minutos_cierre_antes FROM sorteos WHERE id = %s", (sorteo_id,))
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

    caja = uno(db, "SELECT agencia_id FROM cajas WHERE id = %s", (caja_id,))
    if caja is None:
        return jsonify({"error": "Caja no encontrada"}), 404

    agencia = uno(db, "SELECT monto_minimo_jugada FROM agencias WHERE id = %s", (caja["agencia_id"],))
    minimo = float(agencia["monto_minimo_jugada"] or 0) if agencia else 0
    if minimo > 0:
        for j in jugadas:
            if j["monto"] < minimo:
                return jsonify({"error": f"El monto mínimo por jugada es {minimo}"}), 409

    for j in jugadas:
        error_bloqueo = _validar_bloqueos_y_limites(db, caja["agencia_id"], j["sorteo_id"], j["numero_jugado"], j["monto"])
        if error_bloqueo:
            return jsonify({"error": error_bloqueo}), 409

    total = sum(j["monto"] for j in jugadas)
    numero_ticket = str(secrets.randbelow(90000000) + 10000000)
    serial = str(secrets.randbelow(900000000) + 100000000)
    vence_en = datetime.now() + timedelta(days=3)

    cur = ejecutar(
        db,
        """INSERT INTO tickets (agencia_id, caja_id, numero_ticket, serial, moneda, total, vence_en)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (caja["agencia_id"], caja_id, numero_ticket, serial, moneda, total, vence_en),
    )
    ticket_id = cur.fetchone()["id"]

    for j in jugadas:
        ejecutar(
            db,
            """INSERT INTO jugadas (ticket_id, sorteo_id, tipo_jugada, numero_jugado, monto)
               VALUES (%s,%s,%s,%s,%s)""",
            (ticket_id, j["sorteo_id"], j["tipo_jugada"], j["numero_jugado"], j["monto"]),
        )

    return jsonify({
        "ticket_id": ticket_id, "numero_ticket": numero_ticket, "serial": serial,
        "total": total, "vence_en": vence_en.isoformat(timespec="seconds"),
    }), 201


@app.get("/agencias/<int:agencia_id>/ventas")
def ventas_de_agencia(agencia_id):
    db = get_db()
    rows = todos(
        db,
        "SELECT numero_ticket, moneda, total, estado, vendido_en FROM tickets WHERE agencia_id = %s ORDER BY vendido_en DESC",
        (agencia_id,),
    )
    return jsonify([dict(r, vendido_en=r["vendido_en"].isoformat()) for r in rows])


@app.post("/resultados")
def registrar_resultado():
    data = request.get_json()
    db = get_db()
    cur = ejecutar(
        db,
        "INSERT INTO resultados (sorteo_id, fecha, numero_ganador) VALUES (%s,%s,%s) RETURNING id",
        (data["sorteo_id"], data.get("fecha", datetime.now().strftime("%Y-%m-%d")), data["numero_ganador"]),
    )
    return jsonify({"resultado_id": cur.fetchone()["id"]}), 201


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


@app.post("/tickets/<int:ticket_id>/anular")
def anular_ticket(ticket_id):
    db = get_db()
    ticket = uno(db, "SELECT id, agencia_id, estado, vendido_en FROM tickets WHERE id = %s", (ticket_id,))
    if ticket is None:
        return jsonify({"error": "Ticket no encontrado"}), 404
    if ticket["estado"] != "vigente":
        return jsonify({"error": f"Este ticket ya está {ticket['estado']}, no se puede anular"}), 409

    agencia = uno(db, "SELECT tiempo_anulacion_min FROM agencias WHERE id = %s", (ticket["agencia_id"],))
    minutos_limite = agencia["tiempo_anulacion_min"] if agencia else 5

    limite = ticket["vendido_en"] + timedelta(minutes=minutos_limite)
    if datetime.now() > limite:
        return jsonify({"error": f"Ya pasaron los {minutos_limite} minutos permitidos para anular"}), 409

    ejecutar(db, "UPDATE tickets SET estado = 'anulado' WHERE id = %s", (ticket_id,))
    return jsonify({"ok": True, "mensaje": "Ticket anulado"})


@app.post("/tickets/pagar")
def pagar_ticket():
    data = request.get_json()
    numero_ticket = data.get("numero_ticket", "")
    serial = data.get("serial", "")

    db = get_db()
    ticket = uno(db, "SELECT id, estado FROM tickets WHERE numero_ticket = %s AND serial = %s", (numero_ticket, serial))
    if ticket is None:
        return jsonify({"error": "Número de ticket o serial incorrecto"}), 404
    if ticket["estado"] == "anulado":
        return jsonify({"error": "Este ticket fue anulado"}), 409
    if ticket["estado"] == "pagado":
        return jsonify({"error": "Este ticket ya fue pagado"}), 409

    jugadas_ganadoras = todos(
        db,
        "SELECT id, premio FROM jugadas WHERE ticket_id = %s AND estado = 'ganador' AND premio_pagado = 0",
        (ticket["id"],),
    )
    if not jugadas_ganadoras:
        return jsonify({"error": "Este ticket no tiene premios pendientes por pagar"}), 409

    total_pagado = sum(j["premio"] for j in jugadas_ganadoras)
    for j in jugadas_ganadoras:
        ejecutar(db, "UPDATE jugadas SET premio_pagado = 1 WHERE id = %s", (j["id"],))
    ejecutar(db, "UPDATE tickets SET estado = 'pagado' WHERE id = %s", (ticket["id"],))

    return jsonify({"ok": True, "total_pagado": total_pagado, "jugadas_pagadas": len(jugadas_ganadoras)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
