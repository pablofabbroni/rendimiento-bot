from flask import Flask, render_template, jsonify, request
import mysql.connector
from datetime import datetime, timedelta

app = Flask(__name__)

DB_CONFIG = {
    'host': '187.77.96.39',
    'port': 3306,
    'user': 'mysql',
    'password': 'ir6yqrdyjnlzi0xw',
    'database': 'mysql'
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def build_filters(args):
    conditions = []
    params = []

    fecha_desde = args.get('fecha_desde')
    fecha_hasta = args.get('fecha_hasta')
    resultado = args.get('resultado')
    naturaleza = args.get('naturaleza')

    if fecha_desde:
        conditions.append("fecha >= %s")
        params.append(fecha_desde + " 00:00:00")
    if fecha_hasta:
        conditions.append("fecha <= %s")
        params.append(fecha_hasta + " 23:59:59")
    if resultado and resultado != 'todas':
        conditions.append("resultado = %s")
        params.append(resultado)
    if naturaleza and naturaleza != 'todas':
        if naturaleza == 'principal':
            conditions.append("intento = 1")
        elif naturaleza == 'gale1':
            conditions.append("intento = 2")
        elif naturaleza == 'gale2':
            conditions.append("intento = 3")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return where, params

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def stats():
    conn = get_db()
    c = conn.cursor(dictionary=True)
    where, params = build_filters(request.args)

    # Totales de operaciones individuales
    c.execute(f"SELECT COUNT(*) as total, SUM(monto) as volumen FROM operaciones {where}", params)
    row = c.fetchone()
    total = row['total'] or 0
    volumen = float(row['volumen'] or 0)

    # Por resultado individual
    c.execute(f"SELECT resultado, COUNT(*) as cnt, SUM(ganancia) as suma FROM operaciones {where} GROUP BY resultado", params)
    resultados = {r['resultado']: {'cnt': r['cnt'], 'suma': float(r['suma'] or 0)} for r in c.fetchall()}

    ganadas = resultados.get('ganada', {}).get('cnt', 0)
    perdidas = resultados.get('perdida', {}).get('cnt', 0)
    empates = resultados.get('empate', {}).get('cnt', 0)
    ganancia_total = sum(r['suma'] for r in resultados.values())

    # Asertividad por CICLO
    # Un ciclo gana si alguna operacion del ciclo gano
    # Un ciclo pierde solo si todas las operaciones del ciclo perdieron
    where_ciclo = where.replace('WHERE', 'WHERE') if where else 'WHERE'
    c.execute(f"""
        SELECT ciclo_id,
               MAX(CASE WHEN resultado = 'ganada' THEN 1 ELSE 0 END) as ciclo_gano,
               MAX(CASE WHEN resultado = 'empate' THEN 1 ELSE 0 END) as ciclo_empato
        FROM operaciones
        {where}
        GROUP BY ciclo_id
    """, params)
    ciclos = c.fetchall()
    total_ciclos = len(ciclos)
    ciclos_ganados = sum(1 for c2 in ciclos if c2['ciclo_gano'])
    ciclos_empatados = sum(1 for c2 in ciclos if not c2['ciclo_gano'] and c2['ciclo_empato'])
    ciclos_perdidos = total_ciclos - ciclos_ganados - ciclos_empatados
    asertividad = round((ciclos_ganados / total_ciclos * 100), 1) if total_ciclos > 0 else 0

    # Capital inicial y actual
    c.execute(f"SELECT balance_antes FROM operaciones {where} ORDER BY id ASC LIMIT 1", params)
    r = c.fetchone()
    capital_inicial = float(r['balance_antes']) if r else 0

    c.execute(f"SELECT balance_despues FROM operaciones {where} ORDER BY id DESC LIMIT 1", params)
    r = c.fetchone()
    capital_actual = float(r['balance_despues']) if r else 0

    conn.close()
    return jsonify({
        'total': total,
        'total_ciclos': total_ciclos,
        'ganadas': ganadas,
        'perdidas': perdidas,
        'empates': empates,
        'ciclos_ganados': ciclos_ganados,
        'ciclos_perdidos': ciclos_perdidos,
        'ciclos_empatados': ciclos_empatados,
        'asertividad': asertividad,
        'volumen': round(volumen, 2),
        'ganancia_total': round(ganancia_total, 2),
        'capital_inicial': round(capital_inicial, 2),
        'capital_actual': round(capital_actual, 2)
    })

@app.route('/api/evolucion')
def evolucion():
    conn = get_db()
    c = conn.cursor(dictionary=True)
    where, params = build_filters(request.args)

    c.execute(f"""
        SELECT DATE_FORMAT(fecha, '%Y-%m-%d') as dia,
               SUM(ganancia) as ganancia_dia,
               COUNT(*) as operaciones,
               MAX(balance_despues) as balance
        FROM operaciones {where}
        GROUP BY dia ORDER BY dia ASC
    """, params)
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        'dia': r['dia'],
        'ganancia': float(r['ganancia_dia'] or 0),
        'operaciones': r['operaciones'],
        'balance': float(r['balance'] or 0)
    } for r in rows])

@app.route('/api/pares')
def pares():
    conn = get_db()
    c = conn.cursor(dictionary=True)
    where, params = build_filters(request.args)

    c.execute(f"""
        SELECT par,
               COUNT(*) as total,
               SUM(CASE WHEN resultado='ganada' THEN 1 ELSE 0 END) as ganadas,
               SUM(ganancia) as ganancia_total,
               ROUND(SUM(CASE WHEN resultado='ganada' THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) as asertividad
        FROM operaciones {where}
        GROUP BY par ORDER BY asertividad DESC
    """, params)
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        'par': r['par'],
        'total': r['total'],
        'ganadas': r['ganadas'],
        'ganancia_total': float(r['ganancia_total'] or 0),
        'asertividad': float(r['asertividad'] or 0)
    } for r in rows])

@app.route('/api/historial')
def historial():
    conn = get_db()
    c = conn.cursor(dictionary=True)
    where, params = build_filters(request.args)

    c.execute(f"""
        SELECT id, fecha, par, direccion, mercado, monto, expiracion,
               resultado, ganancia, intento, balance_antes, balance_despues
        FROM operaciones {where}
        ORDER BY id DESC LIMIT 100
    """, params)
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        'id': r['id'],
        'fecha': str(r['fecha']),
        'par': r['par'],
        'direccion': r['direccion'].upper(),
        'mercado': r['mercado'],
        'monto': float(r['monto']),
        'expiracion': r['expiracion'],
        'resultado': r['resultado'],
        'ganancia': float(r['ganancia'] or 0),
        'intento': r['intento'],
        'balance_antes': float(r['balance_antes']),
        'balance_despues': float(r['balance_despues']),
        'naturaleza': 'Principal' if r['intento'] == 1 else f"Gale {r['intento']-1}"
    } for r in rows])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
