"""
Este script crea la base de datos desde cero, con el catálogo de
loterías real. Se corre UNA sola vez al preparar el servidor
(Render lo ejecuta automáticamente vía build.sh).
"""
import sqlite3
import os

# Si la base ya existe (ej. en un redeploy), no la recreamos para no
# borrar ventas/resultados ya guardados.
if os.path.exists("loterias.db"):
    print("La base de datos ya existe, no se vuelve a crear.")
else:
    con = sqlite3.connect("loterias.db")
    with open("schema.sql") as f:
        con.executescript(f.read())

    cur = con.cursor()

    loterias = [
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
    cur.executemany(
        "INSERT INTO loterias (nombre, cantidad_numeros, pago_normal, pago_aproximacion, numero_comodin, pago_comodin) VALUES (?,?,?,?,?,?)",
        loterias,
    )

    # Un sorteo de ejemplo (La Granjita, 3:00 PM) para poder hacer pruebas
    cur.execute("SELECT id FROM loterias WHERE nombre = 'LA GRANJITA'")
    loteria_id = cur.fetchone()[0]
    cur.execute("INSERT INTO sorteos (loteria_id, hora) VALUES (?, ?)", (loteria_id, "15:00"))

    con.commit()
    print(f"Base de datos creada con {len(loterias)} loterías cargadas.")
