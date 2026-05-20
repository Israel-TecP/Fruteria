from flask import Flask, json, jsonify, render_template, request, redirect, session, url_for, flash, g
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
import oracledb
from flask import request, abort
import bcrypt

app = Flask(__name__) 
app.config['SESSION_PERMANENT'] = True

def reset_sesiones_activas():
    try:
        conn = pool_login.acquire()
        with conn.cursor() as cur:
            cur.execute("UPDATE ADMIN.USUARIOS SET EN_USO = 'N' WHERE EN_USO = 'S'")
            conn.commit()
            print("Sesiones activas reseteadas correctamente.")
    except Exception as e:
        print(f"Error al resetear sesiones: {e}")
    finally:
        pool_login.release(conn)



pools = {
    "ADMIN": oracledb.create_pool(
        user="ADMIN",
        password="Isr10092005",  # Quite la I para probar el html de mantenimiento
        dsn="localhost:1521/FREEPDB1",
        min=1,
        max=3,
        increment=1
    ),
    "EMPLEADO": oracledb.create_pool(
        user="EMPLEADO",
        password="10092005",
        dsn="localhost:1521/FREEPDB1",
        min=1,
        max=3,
        increment=1
    )
}
app.secret_key = 'Me inmortalizo'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' 

import oracledb

def get_connection():
    if 'conn' not in g:
        rol = session.get('rol')
        if not rol:
            raise Exception("No hay rol activo en sesión")
        if rol not in pools:
            raise Exception(f"Rol desconocido: {rol}")
        g.conn = pools[rol].acquire()
    return g.conn

def reset_sesiones_activas():
    try:
        conn = pool_login.acquire()
        with conn.cursor() as cur:
            cur.execute("UPDATE ADMIN.USUARIOS SET EN_USO = 'N' WHERE EN_USO = 'S'")
            conn.commit()
            print("Sesiones activas reseteadas correctamente.")
    except Exception as e:
        print(f"Error al resetear sesiones: {e}")
    finally:
        pool_login.release(conn)

@app.teardown_request
def close_connection(exception):
    conn = g.pop('conn', None)
    if conn is not None:
        conn.close()

class User(UserMixin):
    def __init__(self, username, rol, acceso_ventas, acceso_caja, acceso_inventario):
        self.id = username
        self.username = username
        self.rol = rol
        self.acceso_ventas = acceso_ventas
        self.acceso_caja = acceso_caja
        self.acceso_inventario = acceso_inventario

pool_login = oracledb.create_pool(
    user="ADMIN",
    password="Isr10092005",
    dsn="localhost:1521/FREEPDB1",
    min=1,
    max=2,
    increment=1
)

reset_sesiones_activas()

@login_manager.user_loader
def load_user(username):
    conn = None
    try:
        conn = pool_login.acquire()
        with conn.cursor() as cur:
            cur.execute("SELECT Usuario, Rol, ACCESO_VENTAS, ACCESO_CAJA, ACCESO_INVENTARIO FROM ADMIN.USUARIOS WHERE Usuario = :1", [username])
            user = cur.fetchone()
            if user:
                return User(username=user[0], rol=user[1], acceso_ventas=user[2],
                           acceso_caja=user[3], acceso_inventario=user[4])
    except Exception as e:
        print(f"Error al cargar usuario: {e}")
        return None 
    finally:
        if conn:
            pool_login.release(conn)
    return None

@app.route('/logout')
@login_required
def logout():
    username = current_user.username
    conn = pool_login.acquire()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE ADMIN.USUARIOS
                SET EN_USO = 'N'
                WHERE USUARIO = :1
            """, [username])
            conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"Error al cerrar sesión: {str(e)}", "danger")
    finally:
        pool_login.release(conn)
    logout_user()
    session.clear()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('login'))

@app.errorhandler(503)
def Mantenimiento(e):
    return render_template("Mantenimiento.html"), 503

@app.before_request
def check_db():
    if request.path.startswith('/static/'):
        return
    try:
        conn = pool_login.acquire()
        pool_login.release(conn)
    except Exception:
        abort(503)

@app.before_request
def verificar_estado_usuario():
    if not current_user.is_authenticated:
        return
        
    conn = pool_login.acquire()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT EN_USO FROM ADMIN.USUARIOS WHERE USUARIO = :1",
                       [current_user.username])
            estado = cur.fetchone()
    finally:
        pool_login.release(conn)

    if not estado or estado[0] != 'S':
        logout_user()
        session.clear()
        flash("Tu sesión ha expirado.", "warning")
        return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        Usuario   = request.form['username'].strip().upper()
        Contraseña = request.form['password']
        try:
            conn = pool_login.acquire()
            with conn.cursor() as cur:
                out_cursor = cur.var(oracledb.DB_TYPE_CURSOR)

                cur.callproc("INICIO_SESION", [Usuario, out_cursor])
                result = out_cursor.getvalue().fetchone()

                if not result:
                    flash('Usuario o contraseña incorrectos', 'danger')
                    return render_template('index.html')

                hash_guardado = result[6]
                if isinstance(hash_guardado, str):
                    hash_guardado = hash_guardado.encode('utf-8') 

                if not bcrypt.checkpw(Contraseña.encode('utf-8'), hash_guardado):
                    flash('Usuario o contraseña incorrectos', 'danger')
                    return render_template('index.html')

                if result[5] == 'S':
                    flash('El usuario ya está en uso, cierra sesión en otro dispositivo.', 'danger')
                    return render_template('index.html')

                cur.execute("""
                    UPDATE ADMIN.USUARIOS SET EN_USO = 'S'
                    WHERE TRIM(USUARIO) = TRIM(:1)
                """, (Usuario,))
                conn.commit()

                user = User(
                    username=result[0], rol=result[1],
                    acceso_ventas=result[2], acceso_caja=result[3],
                    acceso_inventario=result[4]
                )
                login_user(user)
                session['rol'] = user.rol
                session['acceso_ventas'] = user.acceso_ventas
                session['acceso_caja'] = user.acceso_caja
                session['acceso_inventario'] = user.acceso_inventario
                session.permanent = True
                return redirect(url_for('principal'))

        except Exception as e:
            print(f"Error al iniciar sesion: {e}")
            flash('Error al conectar con la base de datos', 'danger')
            return render_template("Mantenimiento.html"), 500

    return render_template('index.html')

@app.route('/principal')
@login_required
def principal():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ADMIN.PRINCIPAL")
    usuarios = cur.fetchall()

    return render_template("principal.html", usuarios=usuarios)

@app.route('/ventas')
@login_required
def ventas():
    if(current_user.acceso_ventas != 'S' and current_user.rol !='ADMIN'):
        flash("No tienes permiso para acceder a esta sección", "danger")    
        return redirect(url_for('principal'))
    carrito = session.get('carrito', [])
    total = sum(float(item['precio']) * int(item['cantidad']) for item in carrito)
    return render_template('ventas.html', carrito=carrito, total=total)

@app.route('/vaciar_carrito')
@login_required
def vaciar_carrito():
    carrito = session.get('carrito', [])
    
    if not carrito:
        session['carrito'] = []
        return redirect(url_for('ventas'))

    conn = get_connection()
    with conn.cursor() as cur:
        for item in carrito:
            cur.execute("""
                UPDATE ADMIN.PRODUCTO 
                SET EN_USO = 'N', CANTIDAD = CANTIDAD + :1
                WHERE CODIGO = :2
            """, [item['cantidad'], item['codigo']])
        
        conn.commit()

    session['carrito'] = []
    session.modified = True
    return redirect(url_for('ventas'))

@app.route('/carrito_eliminar/<codigo>', methods=['POST'])
@login_required
def carrito_eliminar(codigo):
    carrito = session.get('carrito', [])
    
    cantidad_list = [item['cantidad'] for item in carrito if int(item['codigo']) == int(codigo)]
    cantidad = cantidad_list[0] if cantidad_list else 0

    nuevo_carrito = [item for item in carrito if int(item['codigo']) != int(codigo)]

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE ADMIN.PRODUCTO 
            SET CANTIDAD = CANTIDAD + :1
            WHERE CODIGO = :2
        """, [cantidad, codigo])
        conn.commit()

    session['carrito'] = nuevo_carrito
    session.modified = True

    flash(f"Producto {codigo} eliminado del carrito.", "info")
    return redirect(url_for('ventas'))

@app.route('/realizar_venta')
@login_required
def realizar_venta():
    carrito = session.pop("carrito", [])
    session.modified = True

    if not carrito:
        flash("El carrito está vacío.", "warning")
        return redirect(url_for('ventas'))

    try:
        conn = get_connection()
        with conn.cursor() as cur:
            out_cursor = cur.var(oracledb.DB_TYPE_CURSOR)
            cur.callproc("ADMIN.REALIZAR_VENTA", [json.dumps(carrito), out_cursor])
        conn.commit()
        flash("Venta realizada correctamente.", "success")

    except Exception as e:
        session["carrito"] = carrito
        session.modified = True
        conn.rollback()
        print(f"Error al realizar venta: {e}")
        flash("Error al procesar la venta, intente de nuevo.", "danger")

    return redirect(url_for('ventas'))

@app.route('/api/productos',methods=['GET', 'POST'])
@login_required
def productos():
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM ADMIN.API_PRODUCTOS", [])
            Producto = cur.fetchall()
        data = [
            {
                "nombre": p[0],
                "categoria": p[1],
                "precio": p[2],
                "cantidad": p[3],
                "codigo": p[4],
                "t_unidad": p[5],
                "en_uso": p[6]
            }
            for p in Producto
        ]
        return jsonify(data)
    except Exception as e:
        print(f"Error al obtener productos: {e}")
        return jsonify([]), 500
   
@app.route('/agregar_producto', methods=['POST', 'GET'])
@login_required
def agregar_producto():
    seleccionados = request.form.getlist('productos_seleccionados')

    if not seleccionados:
        return redirect(url_for('ventas'))

    # Leer cantidades ANTES de abrir la transacción
    cantidades = {}
    for codigo in seleccionados:
        cant = int(request.form.get(f'cantidad_{codigo}', 1))
        cantidades[codigo] = cant

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            placeholders = ','.join([f':{i+1}' for i in range(len(seleccionados))])

            cur.execute(f"""
                SELECT CODIGO, CANTIDAD, EN_USO
                FROM ADMIN.PRODUCTO
                WHERE CODIGO IN ({placeholders})
                FOR UPDATE
            """, seleccionados)

            filas = cur.fetchall()

            bloqueados = []
            for r in filas:
                codigo, cantidad_db, en_uso = r[0], r[1], r[2]
                if cantidad_db == 0:
                    bloqueados.append((codigo, 'sin_stock'))
                elif en_uso == 'S':
                    bloqueados.append((codigo, 'en_uso'))

            if bloqueados:
                conn.rollback()
                mensajes = [
                    f"{cod} ({'sin stock' if motivo == 'sin_stock' else 'en uso'})"
                    for cod, motivo in bloqueados
                ]
                flash(f"Productos no disponibles: {', '.join(mensajes)}", "danger")
                session['bloqueados'] = [cod for cod, _ in bloqueados]
                return redirect(url_for('ventas'))

            cur.execute(f"""
                SELECT p.NOMBRE, c.CATEGORIA, p.PRECIO, p.CANTIDAD, p.CODIGO, p.EN_USO
                FROM ADMIN.PRODUCTO p
                JOIN ADMIN.CATEGORIA c ON p.CATEGORIA = c.ID_CATE
                WHERE p.CODIGO IN ({placeholders})
                ORDER BY p.CODIGO ASC
            """, seleccionados)
            productos = cur.fetchall()

            if 'carrito' not in session:
                session['carrito'] = []

            for p in productos:
                codigo = p[4]
                cantidad_seleccionada = cantidades.get(str(codigo), 1)
                if not any(item['codigo'] == codigo for item in session['carrito']):
                    session['carrito'].append({
                        "nombre":   p[0],
                        "categoria": p[1],
                        "precio":   p[2],
                        "stock":    p[3],
                        "codigo":   codigo,
                        "cantidad": cantidad_seleccionada
                    })

            for p in productos:
                codigo = p[4]
                cantidad_seleccionada = cantidades.get(str(codigo), 1)
                cur.execute("""
                    UPDATE ADMIN.PRODUCTO
                    SET CANTIDAD = CANTIDAD - :1
                    WHERE CODIGO = :2
                      AND CANTIDAD >= :3
                      AND EN_USO = 'N'
                """, [cantidad_seleccionada, codigo, cantidad_seleccionada])

                if cur.rowcount == 0:
                    conn.rollback()
                    flash(f"Stock insuficiente para el producto {codigo}.", "danger")
                    return redirect(url_for('ventas'))

        conn.commit()
        session.modified = True

    except Exception as e:
        conn.rollback()
        print(f"Error al agregar producto: {e}")
        flash("Error al procesar la solicitud.", "danger")

    return redirect(url_for('ventas'))

@app.route('/Buscar_Productos', methods=['GET'])
def buscar_productos():
    filtro = request.args.get('filtro', '').strip()
    conn = get_connection()
    try:
     with conn.cursor() as cur:
        cur.execute("SELECT * FROM ADMIN.API_PRODUCTOS WHERE NOMBRE LIKE :filtro", {'filtro': f'%{filtro}%'})
        Productos = cur.fetchall()
        data = [
            {
                "nombre": p[0],
                "categoria": p[1],
                "precio": p[2],
                "cantidad": p[3],
                "codigo": p[4],
                "t_unidad": p[5],
                "en_uso": p[6]
            }
            for p in Productos
        ]
        return jsonify(data)
    except Exception as e:
        print(f"Error al obtener productos: {e}")
        return jsonify([]), 500

@app.route('/api/ventas_caja')
@login_required
def api_ventas_caja():
    fecha_fin_fmt = datetime.today().strftime("%d/%m/%y")
    fecha_inicio_fmt = (datetime.today() - timedelta(days=5)).strftime("%d/%m/%y")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT id_v, tipo, monto, descripcion, fecha, hora
                FROM (
                    SELECT id_v, tipo, monto, descripcion, fecha, hora,
                        ROW_NUMBER() OVER (
                            PARTITION BY id_v, fecha
                            ORDER BY hora DESC
                        ) AS rn
                    FROM ADMIN.VIEW_VENTAS_CAJA
                    WHERE TO_DATE(FECHA, 'DD/MM/RR')
                        BETWEEN TO_DATE(:fecha_inicio, 'DD/MM/RR')
                            AND TO_DATE(:fecha_fin, 'DD/MM/RR')
                )
                WHERE rn = 1
                ORDER BY TO_DATE(fecha, 'DD/MM/RR') DESC, hora DESC
            """, {
                "fecha_inicio": fecha_inicio_fmt,
                "fecha_fin": fecha_fin_fmt
            })

            rows = cur.fetchall()   
            print(type(rows[0][5]), rows[0][5])

        return jsonify([
    {
        "id": row[0],
        "tipo": row[1],
        "monto": float(row[2]),
        "descripcion": row[3],
        "fecha": str(row[4])[:10], 
        "hora": row[5].strftime('%H:%M') if hasattr(row[5], 'strftime') else str(row[5])[:5]  # ← toma solo HH:MM
    }
    for row in rows
])

    except Exception as e:
        print("ERROR:", e)
        return jsonify([]), 500

@app.route('/api/ventas_caja/Eliminar/<string:id>', methods=['DELETE'])
@login_required
def api_eliminar_venta_caja(id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.callproc("ADMIN.ELIMINAR_VENTA", [id])
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        print("ERROR:", e)
        return jsonify({"success": False}), 500
    
@app.route('/api/ventas_caja_gasto/Eliminar/<string:id>', methods=['DELETE'])
@login_required
def api_eliminar_venta_caja_gasto(id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE ADMIN.PAGOS_FIJOS SET ESTADO = 'ELIMINADO' WHERE ID_GF = :1", (id,))
            conn.commit()
            return jsonify({"success": True})
    except Exception as e:
        print(f"Error al eliminar gasto de caja: {e}")
        return jsonify({"success": False}), 500

@app.route('/api/filtro_ventas_caja', methods=['GET'])
@login_required
def api_filtro_ventas_caja():
    fecha_inicio_str = request.args.get('fecha_inicio') 
    hora_inicio_str = request.args.get('hora_inicio')   
    fecha_fin_str = request.args.get('fecha_fin')    
    hora_fin_str = request.args.get('hora_fin')         

    # Convertir fechas al formato que usa Oracle (DD-MM-YYYY)
    fecha_inicio_fmt = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").strftime("%d/%m/%y")
    fecha_fin_fmt = datetime.strptime(fecha_fin_str, "%Y-%m-%d").strftime("%d/%m/%y")

    print("Fecha Inicio Formateada:", fecha_inicio_fmt)
    print("Fecha Fin Formateada:", fecha_fin_fmt)
    print("Hora Inicio:", hora_inicio_str)
    print("Hora Fin:", hora_fin_str)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT v.ID_V, 'venta' AS tipo, v.TOTAL AS monto, p.NOMBRE AS descripcion, f.FECHA, h.HORA
                FROM ADMIN.VENTAS v
                LEFT JOIN ADMIN.VP ON ADMIN.VP.CODIGO = V.PRODUCTO
                LEFT JOIN ADMIN.PRODUCTO p ON p.CODIGO = ADMIN.VP.CODIGO
                LEFT JOIN ADMIN.FECHA f ON v.FECHA = f.ID_FECHA
                LEFT JOIN ADMIN.HORA h ON v.HORA = h.ID_HORA
                WHERE v.ESTADO = 'ACTIVO' AND p.NOMBRE IS NOT NULL
                    AND f.FECHA BETWEEN :fecha_inicio AND :fecha_fin
                    AND h.HORA >= :hora_inicio
                    AND h.HORA <= :hora_fin
                ORDER BY f.FECHA DESC, h.HORA DESC
            """, {
                "fecha_inicio": fecha_inicio_fmt,
                "fecha_fin": fecha_fin_fmt,
                "hora_inicio": hora_inicio_str,
                "hora_fin": hora_fin_str
            })
            registros = [
                {
                    "id": r[0],
                    "tipo": r[1],
                    "monto": float(r[2]),
                    "descripcion": r[3],
                    "fecha": r[4].strftime("%d/%m/%y") if hasattr(r[4], "strftime") else str(r[4]),
                    "hora": r[5]
                }
                for r in cur.fetchall()
            ]

        return jsonify(registros)
    except Exception as e:
        print(f"Error al obtener ventas para caja: {e}")
        return jsonify([]), 500

@app.route('/api/ventas_caja/gastos')
@login_required
def gastos():
    fecha_fin_fmt = datetime.today().strftime("%d/%m/%y")
    fecha_inicio_fmt = (datetime.today() - timedelta(days=5)).strftime("%d/%m/%y")
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    pf.ID_GF,
                    'Gasto'      AS tipo,
                    pf.CANTIDAD  AS monto,
                    pf.NOMBRE_GF AS descripcion,
                    f.FECHA,
                    h.HORA
                FROM ADMIN.PAGOS_FIJOS pf
                JOIN ADMIN.FECHA f ON pf.FECHA = f.ID_FECHA
                JOIN ADMIN.HORA h ON h.ID_HORA = pf.HORA
                WHERE TO_DATE(f.FECHA, 'DD/MM/RR')
                    BETWEEN TO_DATE(:fecha_inicio, 'DD/MM/RR')
                        AND TO_DATE(:fecha_fin, 'DD/MM/RR')
                AND pf.ESTADO = 'ACTIVO'
                AND pf.ROWID = (
                    SELECT pf2.ROWID
                    FROM ADMIN.PAGOS_FIJOS pf2
                    JOIN ADMIN.HORA h2 ON h2.ID_HORA = pf2.HORA
                    WHERE pf2.ID_GF   = pf.ID_GF
                      AND pf2.ESTADO  = 'ACTIVO'
                    ORDER BY TO_DATE(
                        (SELECT f2.FECHA FROM ADMIN.FECHA f2 WHERE f2.ID_FECHA = pf2.FECHA),
                        'DD/MM/RR'
                    ) DESC, h2.HORA DESC
                    FETCH FIRST 1 ROWS ONLY
                )
                ORDER BY TO_DATE(f.FECHA, 'DD/MM/RR') DESC, h.HORA DESC
            """, {
                "fecha_inicio": fecha_inicio_fmt,
                "fecha_fin": fecha_fin_fmt
            })

            registros = [
                {
                    "id": r[0],
                    "tipo": r[1],
                    "monto": float(r[2]),
                    "descripcion": r[3],
                    "fecha": r[4].strftime("%Y-%m-%d") if hasattr(r[4], "strftime") else str(r[4]),
                    "hora": r[5].strftime("%H:%M") if hasattr(r[5], "strftime") else str(r[5])
                } for r in cur.fetchall()
            ]
            return jsonify(registros)
    except Exception as e:
        print(f"Error al obtener gastos para caja: {e}")
        return jsonify([]), 500

@app.route('/api/filtro_gastos_caja', methods=['GET'])
@login_required
def api_filtro_gastos_caja():
    fecha_inicio_str = request.args.get('fecha_inicio')
    hora_inicio_str = request.args.get('hora_inicio', '00:00')
    fecha_fin_str = request.args.get('fecha_fin')
    hora_fin_str = request.args.get('hora_fin', '23:59')

    try:
        fecha_inicio_fmt = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").strftime("%d/%m/%y")
        fecha_fin_fmt    = datetime.strptime(fecha_fin_str,    "%Y-%m-%d").strftime("%d/%m/%y")
    except (ValueError, TypeError):
        return jsonify({"error": "Formato de fecha inválido"}), 400

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    pf.ID_GF,
                    'Gasto'      AS tipo,
                    pf.CANTIDAD  AS monto,
                    pf.NOMBRE_GF AS descripcion,
                    f.FECHA,
                    h.HORA
                FROM ADMIN.PAGOS_FIJOS pf
                JOIN ADMIN.FECHA f ON pf.FECHA    = f.ID_FECHA
                JOIN ADMIN.HORA  h ON pf.HORA     = h.ID_HORA
                WHERE pf.ESTADO = 'ACTIVO' and pf.Nombre_GF IS NOT NULL
                  AND TO_DATE(f.FECHA, 'DD/MM/RR')
                      BETWEEN TO_DATE(:fecha_inicio, 'DD/MM/RR')
                          AND TO_DATE(:fecha_fin,    'DD/MM/RR')
                  AND h.HORA BETWEEN :hora_inicio AND :hora_fin
                  AND pf.ROWID = (
                      SELECT pf2.ROWID
                      FROM ADMIN.PAGOS_FIJOS pf2
                      JOIN ADMIN.HORA h2 ON h2.ID_HORA = pf2.HORA
                      WHERE pf2.ID_GF  = pf.ID_GF
                        AND pf2.ESTADO = 'ACTIVO'
                      ORDER BY TO_DATE(
                          (SELECT f2.FECHA FROM ADMIN.FECHA f2 WHERE f2.ID_FECHA = pf2.FECHA),
                          'DD/MM/RR'
                      ) DESC, h2.HORA DESC
                      FETCH FIRST 1 ROWS ONLY
                  )
                ORDER BY TO_DATE(f.FECHA, 'DD/MM/RR') DESC, h.HORA DESC
            """, {
                "fecha_inicio": fecha_inicio_fmt,
                "fecha_fin":    fecha_fin_fmt,
                "hora_inicio":  hora_inicio_str,
                "hora_fin":     hora_fin_str
            })

            registros = [
                {
                    "id":          r[0],
                    "tipo":        r[1],
                    "monto":       float(r[2]),
                    "descripcion": r[3],
                    "fecha":       r[4].strftime("%d/%m/%y") if hasattr(r[4], "strftime") else str(r[4]),
                    "hora":        r[5].strftime("%H:%M")    if hasattr(r[5], "strftime") else str(r[5])
                }
                for r in cur.fetchall()
            ]

        return jsonify(registros)

    except Exception as e:
        print(f"Error al filtrar gastos: {e}")
        return jsonify([]), 500

@app.route('/api/ventas_caja/AgregarGasto', methods=['POST'])
@login_required
def api_agregar_gasto():
    data = request.get_json()
    print(data)
    if not data or "descripcion" not in data or "monto" not in data:
        return jsonify({"error": "Datos incompletos"}), 400

    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.callproc("ADMIN.AGREGAR_GASTO", [
                str(data["descripcion"]),
                float(data["monto"])
            ])
            conn.commit()
        return jsonify({"success": True}), 200

    except Exception as e:
        print(f"Error al agregar gasto: {e}")
        return jsonify({"error": str(e)}), 500
 
@app.route('/caja')
@login_required
def caja():
    if(current_user.acceso_caja != 'S' and current_user.rol !='ADMIN'):
        flash("No tienes permiso para acceder a esta sección", "danger")    
        return redirect(url_for('principal'))
    return render_template('caja.html')

@app.route('/inventario')
@login_required
def inventario():
    if(current_user.acceso_inventario != 'S' and current_user.rol !='ADMIN'):
        flash("No tienes permiso para acceder a esta sección", "danger")    
        return redirect(url_for('principal'))
    conn = get_connection()

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM ADMIN.INVENTARIO ORDER BY NOMBRE ASC")
        productos = cur.fetchall()
    return render_template('inventario.html', productos=productos)

@app.route('/Eliminados')
@login_required
def eliminados():
    conn = get_connection()

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM ADMIN.PRODUCTO WHERE ESTADO = 'INACTIVO' ORDER BY NOMBRE ASC")
        productos = cur.fetchall()
    return render_template('Eliminados.html', eliminados=productos)

@app.route('/restaurar_producto', methods=['POST'])
@login_required
def restaurar_producto():
    codigo = request.form.get('codigo_restaurar')
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("UPDATE ADMIN.PRODUCTO SET ESTADO = 'ACTIVO' WHERE CODIGO = :1", (codigo,))
        conn.commit()
    return redirect('/Eliminados')

@app.route('/agregar_producto_inventario', methods=['POST'])
@login_required
def agregar_producto_inventario():
    nombre = request.form['Pnombre']
    precio = float(request.form['Pprecio'])
    unidad = request.form['Punidad']
    cantidad_raw = float(request.form['Pcantidad'])
    merma = float(request.form['Pmerma'])
    categoria = int(request.form.get('Pcategoria'))

    if unidad == 'Kilo':
        cantidad = cantidad_raw
    else:
        if not cantidad_raw.is_integer():
            flash('La cantidad en piezas o bolsas debe ser un número entero.', 'danger')
            return redirect(url_for('inventario'))
        cantidad = int(cantidad_raw)

    if merma >= cantidad:
        flash('La merma debe ser menor que la cantidad total.', 'danger')
        return redirect(url_for('inventario'))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM ADMIN.PRODUCTO 
        WHERE UPPER(NOMBRE) = UPPER(:1) 
        AND UPPER(T_UNIDAD) = UPPER(:2)
    """, (nombre, unidad))
    
    if cursor.fetchone()[0] > 0:
        flash("Ya existe un producto con ese nombre y tipo de embolsado.", "danger")
        return redirect(url_for('inventario'))

    try:
        cursor.callproc("ADMIN.INSERTAR_PRODUCTO", [
            nombre, precio, cantidad, merma, unidad, categoria
        ])
    except Exception as e:
        conn.rollback()
        flash(f'Error al agregar el producto: {e}', 'danger')
    else:
        flash('Producto agregado correctamente', 'success')
    finally:
        cursor.close()
    return redirect('/inventario')

@app.route('/actualizar_inventario', methods=['POST'])
@login_required
def actualizar_inventario():
    codigo   = request.form.get('codigo')
    nombre   = request.form.get('nombre')
    precio   = float(request.form.get('precio'))
    cantidad = float(request.form.get('cantidad'))  # valor real del form
    unidad   = request.form['unidad']
    merma    = float(request.form['merma'])
    categoria = request.form['categoria']

    # Validar y convertir cantidad según unidad
    if unidad == 'Kilo':
        if cantidad <= 0:
            flash('La cantidad en kilos debe ser un número positivo.', 'danger')
            return redirect(url_for('inventario'))
    else:
        if not cantidad.is_integer():
            flash('La cantidad en piezas o bolsas debe ser un número entero.', 'danger')
            return redirect(url_for('inventario'))
        cantidad = int(cantidad)

    if merma >= cantidad:
        flash('La merma debe ser menor que la cantidad total.', 'danger')
        return redirect(url_for('inventario'))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("INSERT INTO ADMIN.MERMA (CANTIDAD) VALUES (:1)", (merma,))
    cursor.execute("SELECT MAX(ID_M) FROM ADMIN.MERMA")
    id_merma = cursor.fetchone()[0]

    try:
        cursor.execute("""
        UPDATE ADMIN.PRODUCTO
        SET NOMBRE = :1, PRECIO = :2, CANTIDAD = :3,
            T_UNIDAD = :4, MERMA = :5, CATEGORIA = :6
        WHERE CODIGO = :7
        """, (nombre, precio, cantidad, unidad, id_merma, categoria, codigo))
    except oracledb.IntegrityError as e:
        if "ORA-00001" in str(e):  # Unique constraint violated
            flash("Ya existe un producto con ese nombre y unidad.", "danger")
            conn.rollback()
            return redirect(url_for('inventario'))

    conn.commit()
    flash("Producto actualizado correctamente.", "success")
    return redirect('/inventario')

@app.route('/eliminar_producto', methods=['POST'])
@login_required
def eliminar_producto():
    codigo = request.form.get('codigo_eliminar') 
    print("Código a eliminar:", codigo)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE ADMIN.PRODUCTO
        SET ESTADO = 'INACTIVO'
        WHERE CODIGO = :1
    """, (codigo,))
    conn.commit()
    return redirect('/inventario')

@app.route('/Buscar_Producto', methods=['POST'])
@login_required
def buscar_producto():
    busqueda = request.form['busqueda'].strip()
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM ADMIN.PRODUCTO
            WHERE NOMBRE LIKE :busqueda OR CODIGO LIKE :busqueda
        """, {'busqueda': f'%{busqueda}%'})
        productos = cur.fetchall()
    return render_template('inventario.html', productos=productos)

@app.route('/Administrar_usuarios')
@login_required
def admin_usuarios():
    if session.get('rol') == 'ADMIN':
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT ID_USUARIO, USUARIO, CONTRASENA, ROL, ESTADO, FOTO,
               ACCESO_VENTAS, ACCESO_CAJA, ACCESO_INVENTARIO, EN_USO
            FROM ADMIN.USUARIOS WHERE ESTADO = 'ACTIVO'
            ORDER BY ID_USUARIO
        """)
        usuarios = cur.fetchall()
        print(usuarios)
        return render_template(usuarios=usuarios)
    else:
        flash("No tienes permiso para acceder a esta sección", "danger")    
        return redirect(url_for('principal'))

EXTENSIONES = {'png', 'jpg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in EXTENSIONES

@app.route('/crear_usuario', methods=['POST'])
@login_required
def crear_usuario():
    nombre = request.form['nombre'].strip().upper()
    contrasena = request.form['contrasena']
    hash_contrasena = bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt())
    hash_str = hash_contrasena.decode('utf-8')
    rol = request.form['rol']
    estado = request.form['estado']
    foto = request.files['foto']

    filename = None
    if foto and foto.filename != '' and allowed_file(foto.filename):
        filename = secure_filename(foto.filename)
        foto.save(os.path.join('static/uploads', filename))
    else:
        filename = 'default.png'

    conn = get_connection()
    cur = conn.cursor()
    acceso_ventas = 'S' if 'acceso_ventas' in request.form else 'N'
    acceso_caja = 'S' if 'acceso_caja' in request.form else 'N'
    acceso_inventario = 'S' if 'acceso_inventario' in request.form else 'N'

    try:
        cur.execute("""
            SELECT COUNT(*) FROM ADMIN.USUARIOS 
            WHERE UPPER(USUARIO) = UPPER(:1)
        """, (nombre,))
        if cur.fetchone()[0] > 0:
            flash("Ya existe un usuario con ese nombre.", "danger")
            return redirect(url_for('principal'))
        cur.execute("""
            INSERT INTO ADMIN.USUARIOS (USUARIO, CONTRASENA, ROL, ESTADO, FOTO, ACCESO_VENTAS, ACCESO_CAJA, ACCESO_INVENTARIO)
            VALUES (:1, :2, :3, :4, :5, :6, :7, :8)
""", (nombre, hash_str, rol, estado, filename, acceso_ventas, acceso_caja, acceso_inventario))

        conn.commit()
        flash("Usuario creado correctamente", "success")
    except Exception as e:
        conn.rollback()
        flash("Error al crear el usuario.", "danger")
    return redirect(url_for('principal'))

@app.route('/editar_usuario', methods=['POST'])
@login_required
def editar_usuario():
    id_usuario = request.form['id_usuario']
    nombre = request.form['nombre']
    contrasena = request.form['contrasena']
    hash_contrasena = bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt())
    hash_str = hash_contrasena.decode('utf-8')
    rol = request.form.get('rol')
    estado = request.form['estado']
    foto = request.files['foto']

    filename = request.form.get('foto_actual', 'default.png')
    if foto and foto.filename != '':
        if not allowed_file(foto.filename):
            flash("Tipo de archivo no permitido. Solo se permiten PNG y JPG.", "danger")
            return redirect(url_for('principal'))
        filename = secure_filename(foto.filename)
        foto.save(os.path.join('static/uploads', filename))

    conn = get_connection()
    cur = conn.cursor()
    acceso_ventas = 'S' if 'acceso_ventas' in request.form else 'N'
    acceso_caja = 'S' if 'acceso_caja' in request.form else 'N'
    acceso_inventario = 'S' if 'acceso_inventario' in request.form else 'N'
    if rol == 'EMPLEADO' and not (acceso_ventas or acceso_caja or acceso_inventario):
        flash("Debe seleccionar al menos un permiso para el empleado.", "danger")
        return redirect(url_for('principal'))

    cur.execute("""
    UPDATE ADMIN.USUARIOS SET USUARIO = :1, CONTRASENA = :2, ROL = :3, ESTADO = :4, FOTO = :5, ACCESO_VENTAS = :6, ACCESO_CAJA = :7, ACCESO_INVENTARIO = :8
    WHERE ID_USUARIO = :9
""", (nombre, hash_str, rol, estado, filename, acceso_ventas, acceso_caja, acceso_inventario, id_usuario))

    conn.commit()
    flash("Usuario actualizado correctamente", "success")
    return redirect(url_for('principal'))

@app.route('/eliminar_usuario', methods=['POST'])
@login_required
def eliminar_usuario():
    id_usuario = request.form['id_usuario']
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM ADMIN.USUARIOS
        WHERE ID_USUARIO = :1
    """, (id_usuario,))
    conn.commit()
    flash("Usuario eliminado correctamente", "success")
    return redirect(url_for('principal'))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=False)