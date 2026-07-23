"""
Script de una sola vez: crea los sorteos (horarios) reales de cada
lotería, según lo definido para el sistema.
"""
import psycopg2
import os

DATABASE_URL = os.environ["DATABASE_URL"]

# Loterías con horario normal: cada hora, en punto, de 8am a 7pm
HORARIO_NORMAL = [f"{h:02d}:00" for h in range(8, 20)]
# Loterías con horario a la media hora (ej. 8:30, 9:30... 7:30pm)
HORARIO_30 = [f"{h:02d}:30" for h in range(8, 20)]
# Terminalito: 9:15am a 7:15pm
HORARIO_15 = [f"{h:02d}:15" for h in range(9, 20)]
# Animalitos La Ricachona: 9:10am a 7:10pm
HORARIO_10 = [f"{h:02d}:10" for h in range(9, 20)]

LOTERIAS_CON_HORARIO = {
    "LOTTO ACTIVO": HORARIO_NORMAL,
    "LA GRANJITA": HORARIO_NORMAL,
    "SELVA PLUS": HORARIO_NORMAL,
    "CHANCE ANIMALITO": HORARIO_NORMAL,
    "GUACHARO ACTIVO": HORARIO_NORMAL,
    "TRIOACTIVO": HORARIO_NORMAL,
    "TERMINAL TRIO ACTIVO": HORARIO_NORMAL,
    "TRIPLE LA RICACHONA": HORARIO_NORMAL,
    "TERMINAL LA RICACHONA": HORARIO_NORMAL,
    "GUACHARITO MILLONARIO": HORARIO_30,
    "LOTTOREY": HORARIO_30,
    "LOTTOINTERNACIONAL": HORARIO_30,
    "TERMINALITO": HORARIO_15,
    "ANIMALITOS LA RICACHONA": HORARIO_10,
}

con = psycopg2.connect(DATABASE_URL)
cur = con.cursor()

total_creados = 0
for nombre, horas in LOTERIAS_CON_HORARIO.items():
    cur.execute("SELECT id FROM loterias WHERE nombre = %s", (nombre,))
    fila = cur.fetchone()
    if fila is None:
        print(f"AVISO: no encontré la lotería '{nombre}', se omite")
        continue
    loteria_id = fila[0]
    for hora in horas:
        cur.execute("SELECT id FROM sorteos WHERE loteria_id = %s AND hora = %s", (loteria_id, hora))
        if cur.fetchone() is None:
            cur.execute("INSERT INTO sorteos (loteria_id, hora) VALUES (%s, %s)", (loteria_id, hora))
            total_creados += 1

con.commit()
print(f"Listo: {total_creados} sorteos nuevos creados.")

cur.execute("""
    SELECT l.nombre, COUNT(*) FROM sorteos s JOIN loterias l ON l.id = s.loteria_id
    GROUP BY l.nombre ORDER BY l.nombre
""")
print("Resumen de sorteos por lotería:")
for nombre, cantidad in cur.fetchall():
    print(f"  {nombre}: {cantidad}")
