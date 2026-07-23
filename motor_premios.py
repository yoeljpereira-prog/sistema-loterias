"""
Motor de cálculo de premios (versión PostgreSQL).

Misma lógica que ya probamos con SQLite, adaptada a psycopg2:
- placeholders %s en vez de ?
- las filas se acceden por nombre de columna (row["campo"]),
  porque la conexión usa RealDictCursor
"""

from datetime import datetime
from zoneinfo import ZoneInfo

TZ_VENEZUELA = ZoneInfo("America/Caracas")


def ahora_local():
    return datetime.now(TZ_VENEZUELA).replace(tzinfo=None)


def procesar_resultado(con, resultado_id):
    cur = con.cursor()

    cur.execute("""
        SELECT r.id AS resultado_id, r.sorteo_id, r.fecha, r.numero_ganador, r.estado,
               l.pago_normal, l.pago_aproximacion, l.numero_comodin, l.pago_comodin
        FROM resultados r
        JOIN sorteos s ON s.id = r.sorteo_id
        JOIN loterias l ON l.id = s.loteria_id
        WHERE r.id = %s
    """, (resultado_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No existe el resultado {resultado_id}")

    if row["estado"] == "procesado":
        raise ValueError("Este resultado ya fue procesado. Usa 'reversar' primero si necesitas corregirlo.")

    sorteo_id = row["sorteo_id"]
    numero_ganador = row["numero_ganador"]
    pago_normal = row["pago_normal"]
    pago_aproximacion = row["pago_aproximacion"]
    numero_comodin = row["numero_comodin"]
    pago_comodin = row["pago_comodin"]

    if numero_comodin is not None and numero_ganador == numero_comodin:
        proporcion_normal = pago_comodin
    else:
        proporcion_normal = pago_normal

    vecinos_aproximacion = set()
    if pago_aproximacion and numero_ganador.isdigit():
        n = int(numero_ganador)
        vecinos_aproximacion = {str(n - 1), str(n + 1)}

    cur.execute("""
        SELECT j.id, j.numero_jugado, j.monto
        FROM jugadas j
        JOIN tickets t ON t.id = j.ticket_id
        WHERE j.sorteo_id = %s AND j.estado = 'pendiente'
    """, (sorteo_id,))
    jugadas = cur.fetchall()

    ganadoras = 0
    perdedoras = 0
    total_premios = 0.0

    for jugada in jugadas:
        jugada_id = jugada["id"]
        numero_jugado = jugada["numero_jugado"]
        monto = jugada["monto"]

        if numero_jugado == numero_ganador:
            premio = monto * proporcion_normal
            cur.execute("UPDATE jugadas SET estado = 'ganador', premio = %s WHERE id = %s", (premio, jugada_id))
            ganadoras += 1
            total_premios += premio
        elif numero_jugado in vecinos_aproximacion:
            premio = monto * pago_aproximacion
            cur.execute("UPDATE jugadas SET estado = 'ganador', premio = %s WHERE id = %s", (premio, jugada_id))
            ganadoras += 1
            total_premios += premio
        else:
            cur.execute("UPDATE jugadas SET estado = 'perdedor' WHERE id = %s", (jugada_id,))
            perdedoras += 1

    cur.execute(
        "UPDATE resultados SET estado = 'procesado', procesado_en = %s WHERE id = %s",
        (ahora.local(), resultado_id),
    )
    con.commit()

    return {
        "numero_ganador": numero_ganador,
        "jugadas_ganadoras": ganadoras,
        "jugadas_perdedoras": perdedoras,
        "total_premios": total_premios,
    }


def reversar_resultado(con, resultado_id):
    cur = con.cursor()
    cur.execute("SELECT sorteo_id, estado FROM resultados WHERE id = %s", (resultado_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No existe el resultado {resultado_id}")
    if row["estado"] != "procesado":
        raise ValueError("Este resultado no está procesado, no hay nada que reversar.")

    sorteo_id = row["sorteo_id"]
    cur.execute("""
        UPDATE jugadas SET estado = 'pendiente', premio = 0
        WHERE sorteo_id = %s AND estado IN ('ganador', 'perdedor')
    """, (sorteo_id,))
    cur.execute("UPDATE resultados SET estado = 'pendiente', procesado_en = NULL WHERE id = %s", (resultado_id,))
    con.commit()
