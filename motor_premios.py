"""
Motor de cálculo de premios.

Regla en palabras simples:
- Un resultado (lotería + sorteo + fecha) se carga con su número ganador.
- Al "procesar" ese resultado, buscamos todas las jugadas pendientes de
  ese mismo sorteo y fecha.
- Si el número jugado es igual al número ganador -> jugada GANADORA,
  premio = monto apostado x proporción de pago de la lotería.
- Si el número ganador es el "número comodín" de esa lotería, se usa
  la proporción de pago del comodín en vez de la normal.
- Si la lotería tiene "aproximación" (paga por acertar el número
  inmediatamente arriba o abajo) y la jugada es ese vecino del número
  ganador, también gana pero con la proporción de aproximación.
- Todo lo que no coincide queda como PERDEDORA.
"""

import sqlite3
from datetime import datetime


def procesar_resultado(con, resultado_id):
    """
    Procesa un resultado: calcula los premios de todas las jugadas
    pendientes de ese sorteo+fecha, y marca el resultado como 'procesado'.
    Devuelve un resumen para mostrarle al usuario.
    """
    cur = con.cursor()

    # 1. Traer el resultado y la info de su lotería
    cur.execute("""
        SELECT r.id, r.sorteo_id, r.fecha, r.numero_ganador, r.estado,
               l.id, l.pago_normal, l.pago_aproximacion, l.numero_comodin, l.pago_comodin
        FROM resultados r
        JOIN sorteos s ON s.id = r.sorteo_id
        JOIN loterias l ON l.id = s.loteria_id
        WHERE r.id = ?
    """, (resultado_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No existe el resultado {resultado_id}")

    (res_id, sorteo_id, fecha, numero_ganador, estado,
     loteria_id, pago_normal, pago_aproximacion, numero_comodin, pago_comodin) = row

    if estado == "procesado":
        raise ValueError("Este resultado ya fue procesado. Usa 'reversar' primero si necesitas corregirlo.")

    # 2. Determinar la proporción de pago según si es número normal o comodín
    if numero_comodin is not None and numero_ganador == numero_comodin:
        proporcion_normal = pago_comodin
    else:
        proporcion_normal = pago_normal

    # Vecinos para aproximación (solo aplica a números, no a tripletas)
    vecinos_aproximacion = set()
    if pago_aproximacion and numero_ganador.isdigit():
        n = int(numero_ganador)
        vecinos_aproximacion = {str(n - 1), str(n + 1)}

    # 3. Buscar jugadas pendientes de ese sorteo (todas las de ese sorteo,
    #    sin importar de qué agencia/ticket vengan)
    cur.execute("""
        SELECT j.id, j.numero_jugado, j.monto
        FROM jugadas j
        JOIN tickets t ON t.id = j.ticket_id
        WHERE j.sorteo_id = ? AND j.estado = 'pendiente'
    """, (sorteo_id,))
    jugadas = cur.fetchall()

    ganadoras = 0
    perdedoras = 0
    total_premios = 0.0

    for jugada_id, numero_jugado, monto in jugadas:
        if numero_jugado == numero_ganador:
            premio = monto * proporcion_normal
            cur.execute(
                "UPDATE jugadas SET estado = 'ganador', premio = ? WHERE id = ?",
                (premio, jugada_id),
            )
            ganadoras += 1
            total_premios += premio
        elif numero_jugado in vecinos_aproximacion:
            premio = monto * pago_aproximacion
            cur.execute(
                "UPDATE jugadas SET estado = 'ganador', premio = ? WHERE id = ?",
                (premio, jugada_id),
            )
            ganadoras += 1
            total_premios += premio
        else:
            cur.execute(
                "UPDATE jugadas SET estado = 'perdedor' WHERE id = ?",
                (jugada_id,),
            )
            perdedoras += 1

    # 4. Marcar el resultado como procesado
    cur.execute(
        "UPDATE resultados SET estado = 'procesado', procesado_en = ? WHERE id = ?",
        (datetime.now().isoformat(timespec="seconds"), res_id),
    )
    con.commit()

    return {
        "numero_ganador": numero_ganador,
        "jugadas_ganadoras": ganadoras,
        "jugadas_perdedoras": perdedoras,
        "total_premios": total_premios,
    }


def reversar_resultado(con, resultado_id):
    """
    Reversa un resultado ya procesado: regresa sus jugadas a 'pendiente'
    (borra el premio calculado) para poder corregir el número y procesar
    de nuevo.
    """
    cur = con.cursor()
    cur.execute("SELECT sorteo_id, estado FROM resultados WHERE id = ?", (resultado_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No existe el resultado {resultado_id}")
    sorteo_id, estado = row
    if estado != "procesado":
        raise ValueError("Este resultado no está procesado, no hay nada que reversar.")

    cur.execute("""
        UPDATE jugadas SET estado = 'pendiente', premio = 0
        WHERE sorteo_id = ? AND estado IN ('ganador', 'perdedor')
    """, (sorteo_id,))
    cur.execute("UPDATE resultados SET estado = 'pendiente', procesado_en = NULL WHERE id = ?", (resultado_id,))
    con.commit()
