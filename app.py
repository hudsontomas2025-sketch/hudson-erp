import os
import io
import urllib.parse
from datetime import datetime
import folium
from fpdf import FPDF
import pandas as pd
import plotly.express as px
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, Boolean, create_engine, text
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import streamlit as st
from streamlit_folium import st_folium

# ========================================================
# 1. MODELOS Y PERSISTENCIA (SQLAlchemy / SQLite)
# ========================================================
Base = declarative_base()
engine = create_engine("sqlite:///hudson_master_erp.db", echo=False)
SessionLocal = sessionmaker(bind=engine)

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    rol = Column(String(30), default="ADMIN")  # 'ADMIN' o 'MOSTRADOR'
    activo = Column(Boolean, default=True)

class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(50), default="Taller Mecánico")
    telefono = Column(String(50))
    ciudad = Column(String(100), default="Concordia")
    direccion = Column(String(150), default="Centro")
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    saldo_cuenta_corriente = Column(Float, default=0.0)
    vehiculo = Column(String(100), nullable=True, default="")
    numero_motor = Column(String(100), nullable=True, default="")
    numero_chasis = Column(String(100), nullable=True, default="")
    pedidos = relationship("Pedido", back_populates="cliente", cascade="all, delete-orphan")

class Repuesto(Base):
    __tablename__ = "repuestos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), unique=True, nullable=False)
    descripcion = Column(String(150), nullable=False)
    marca = Column(String(50), default="Alternativo")
    rubro = Column(String(50), default="Frenos y Suspensión")
    costo = Column(Float, default=0.0)
    precio_venta = Column(Float, default=0.0)
    stock = Column(Integer, default=5)
    stock_minimo = Column(Integer, default=2)
    ubicacion = Column(String(50), default="Estantería 1")

class Pedido(Base):
    __tablename__ = "pedidos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    detalle = Column(Text)
    canal = Column(String(50), default="Mostrador / Local")
    estado = Column(String(50), default="Entregado")
    costo_total = Column(Float, default=0.0)
    precio_total = Column(Float, default=0.0)
    metodo_pago = Column(String(50), default="Efectivo")
    monto_abonado = Column(Float, default=0.0)
    vuelto = Column(Float, default=0.0)
    cliente = relationship("Cliente", back_populates="pedidos")

class MovimientoCaja(Base):
    __tablename__ = "movimientos_caja"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    tipo = Column(String(20))  # INGRESO_VENTA, APERTURA, EGRESO, COBRO_CC
    concepto = Column(String(150))
    medio = Column(String(50), default="Efectivo")
    monto = Column(Float, default=0.0)
    usuario = Column(String(50), default="tomas")

Base.metadata.create_all(engine)

# Migración en caliente para SQLite
with engine.connect() as conn:
    cols_cliente = [row[1] for row in conn.execute(text("PRAGMA table_info(clientes)")).fetchall()]
    if "vehiculo" not in cols_cliente:
        conn.execute(text("ALTER TABLE clientes ADD COLUMN vehiculo VARCHAR(100)"))
    if "numero_motor" not in cols_cliente:
        conn.execute(text("ALTER TABLE clientes ADD COLUMN numero_motor VARCHAR(100)"))
    if "numero_chasis" not in cols_cliente:
        conn.execute(text("ALTER TABLE clientes ADD COLUMN numero_chasis VARCHAR(100)"))
    conn.commit()

session_init = SessionLocal()
if not session_init.query(Usuario).filter(Usuario.username == "tomas").first():
    session_init.add(Usuario(nombre="Tomas Hudson", username="tomas", password="123", rol="ADMIN", activo=True))
    session_init.commit()
if not session_init.query(Usuario).filter(Usuario.username == "caja").first():
    session_init.add(Usuario(nombre="Operador Mostrador", username="caja", password="123", rol="MOSTRADOR", activo=True))
    session_init.commit()
if session_init.query(Repuesto).count() == 0:
    session_init.add(Repuesto(codigo="FR-001", descripcion="Pastillas de Freno Gol Trend", marca="Fras-le", rubro="Frenos y Suspensión", costo=15000.0, precio_venta=28000.0, stock=8, stock_minimo=3, ubicacion="A-12"))
    session_init.add(Repuesto(codigo="AM-104", descripcion="Amortiguador Delantero Hilux", marca="Corven", rubro="Frenos y Suspensión", costo=45000.0, precio_venta=79000.0, stock=4, stock_minimo=2, ubicacion="B-03"))
    session_init.add(Repuesto(codigo="EM-205", descripcion="Kit Distribución Completo Ka 1.5", marca="Gates", rubro="Motor", costo=32000.0, precio_venta=56000.0, stock=2, stock_minimo=3, ubicacion="C-01"))
    session_init.add(Repuesto(codigo="FL-301", descripcion="Filtro de Aceite Hilux / SW4", marca="Mann", rubro="Filtros y Aceites", costo=8500.0, precio_venta=15500.0, stock=12, stock_minimo=4, ubicacion="D-04"))
    session_init.commit()
session_init.close()

# ========================================================
# 2. CONFIGURACIÓN VISUAL & HELPERS
# ========================================================
st.set_page_config(page_title="Hudson Repuestos | ERP & CRM", page_icon="⚙️", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #1a1e24; color: #f1f5f9; }
section[data-testid="stSidebar"] { background-color: #f8fafc !important; }
section[data-testid="stSidebar"] * { color: #1e293b !important; }
.main-title { font-size: 2.1rem; font-weight: 800; color: #ffffff; margin-bottom: 2px; }
.main-subtitle { font-size: 0.95rem; color: #94a3b8; margin-bottom: 25px; }
.kpi-card { background-color: #212936; border: 1px solid #2e384d; border-radius: 10px; padding: 16px; }
.kpi-title { color: #8da2ba; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; }
.kpi-value { color: #38bdf8; font-size: 1.8rem; font-weight: 700; margin-top: 4px; }
.vuelto-banner { background-color: #14532d; border: 2px solid #22c55e; border-radius: 10px; padding: 16px; text-align: center; color: white; margin: 15px 0; }
.vuelto-txt { font-size: 2.8rem; font-weight: 900; color: #86efac; }
.danger-card { background-color: #450a0a; border: 1px solid #dc2626; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
.author-footer { text-align: center; border-top: 1px solid #334155; padding-top: 18px; margin-top: 45px; font-size: 0.85rem; color: #94a3b8; }
.badge-admin { background-color: #0284c7; color: white; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; }
.ficha-auto { background-color: #1e293b; border-left: 4px solid #38bdf8; padding: 10px 14px; border-radius: 4px; margin-top: 8px; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

def fmt(v):
    if v is None:
        return "$0"
    try:
        val = float(v)
    except (ValueError, TypeError):
        return "$0"
    return f"${val:,.0f}".replace(",", ".")

def limpiar_telefono(tel):
    if not tel:
        return ""
    num = "".join(filter(str.isdigit, str(tel)))
    if num.startswith("0"):
        num = num[1:]
    if not num.startswith("54"):
        num = "549" + num
    return num

class PDFTicket(FPDF):
    def __init__(self):
        super().__init__(format=(80, 160))
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 5, "HUDSON REPUESTOS", ln=True, align="C")
        self.set_font("Helvetica", size=7)
        self.cell(0, 4, "Alvear 924, Concordia, Entre Rios", ln=True, align="C")
        self.cell(0, 4, "Tomas Hudson | IVA Resp. Inscripto", ln=True, align="C")
        self.line(4, self.get_y()+2, 76, self.get_y()+2)
        self.ln(4)

def generar_ticket_pdf(pedido_id, fecha, cliente_nom, items, total, medio, abono, vuelto):
    pdf = PDFTicket()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 4, f"TICKET #{pedido_id} - MOSTRADOR", ln=True)
    pdf.set_font("Helvetica", size=7)
    pdf.cell(0, 4, f"Fecha: {fecha.strftime('%d/%m/%Y %H:%M')}", ln=True)
    pdf.cell(0, 4, f"Cliente: {cliente_nom}", ln=True)
    pdf.cell(0, 4, f"Condicion: {medio}", ln=True)
    pdf.line(4, self_y := pdf.get_y()+1, 76, self_y)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 7)
    pdf.cell(38, 4, "Articulo", 0)
    pdf.cell(10, 4, "Cant", 0, align="C")
    pdf.cell(24, 4, "Total", 0, ln=True, align="R")
    pdf.set_font("Helvetica", size=7)

    for it in items:
        pdf.cell(38, 4, it['desc'][:19], 0)
        pdf.cell(10, 4, str(it['cant']), 0, align="C")
        pdf.cell(24, 4, fmt(it['subtotal']), 0, ln=True, align="R")

    pdf.line(4, self_y2 := pdf.get_y()+1, 76, self_y2)
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(42, 5, "TOTAL:", 0)
    pdf.cell(30, 5, fmt(total), 0, ln=True, align="R")

    if medio == "Efectivo":
        pdf.set_font("Helvetica", size=7)
        pdf.cell(42, 4, "Abono:", 0)
        pdf.cell(30, 4, fmt(abono), 0, ln=True, align="R")
        pdf.cell(42, 4, "Vuelto:", 0)
        pdf.cell(30, 4, fmt(vuelto), 0, ln=True, align="R")

    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 6)
    pdf.cell(0, 4, "Gracias por su compra en Hudson Repuestos!", ln=True, align="C")
    return bytes(pdf.output())

# ========================================================
# 3. CONTROL DE SESIÓN
# ========================================================
if "user" not in st.session_state:
    st.session_state["user"] = None

if "cart" not in st.session_state:
    st.session_state["cart"] = []

if "billete_extra" not in st.session_state:
    st.session_state["billete_extra"] = 0.0

if "ultima_venta" not in st.session_state:
    st.session_state["ultima_venta"] = None

session = SessionLocal()

# ========================================================
# ========================================================
# 4. LOGIN (CON LOGO, BOTÓN AZUL OSCURO Y SIN CONTRASEÑA)
# ========================================================
if st.session_state["user"] is None:
    st.markdown("""
    <div style="text-align: center; margin-top: 25px; margin-bottom: 20px;">
        <div style="display: inline-block; background: #0f172a; padding: 18px 26px; border-radius: 50%; border: 3px solid #0284c7; box-shadow: 0 4px 20px rgba(2, 132, 199, 0.35);">
            <span style="font-size: 55px;">⚙️🏎️</span>
        </div>
        <div class="main-title" style="margin-top: 15px; letter-spacing: 1.5px;">HUDSON REPUESTOS</div>
        <p style="color: #94a3b8; font-size: 0.95rem; margin-top: -4px;">
            Sistema de Gestión Integral ERP & CRM • Alvear 924, Concordia, Entre Ríos
        </p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 1.4, 1])
    with c2:
        with st.form("f_login"):
            st.markdown("<h4 style='text-align: center; color: #f8fafc; margin-bottom: 18px;'>Acceso al Sistema</h4>", unsafe_allow_html=True)
            u = st.text_input("Usuario", placeholder="Ej: tomas o caja")
            submit = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
            
            if submit:
                u_clean = u.strip().lower()
                usr = session.query(Usuario).filter(Usuario.username == u_clean).first()
                if usr:
                    if not usr.activo:
                        st.error("⚠️ Este usuario se encuentra suspendido. Contacte a Tomas Hudson.")
                    else:
                        st.session_state["user"] = {"id": usr.id, "nombre": usr.nombre, "rol": usr.rol, "username": usr.username}
                        st.rerun()
                else:
                    st.error("❌ Usuario no encontrado. Ingrese 'tomas' o 'caja'.")
        
        st.markdown("""
        <div style="text-align: center; margin-top: 15px; color: #64748b; font-size: 0.85rem;">
            ℹ️ <b>Administración:</b> <code>tomas</code> | <b>Mostrador:</b> <code>caja</code>
        </div>
        """, unsafe_allow_html=True)
    st.stop() (u_act["rol"] == "ADMIN")

# ========================================================
# 5. MENÚ LATERAL (ARQUEO SOLO VISIBLE PARA ADMINISTRADOR)
# ========================================================
with st.sidebar:
    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 12px;">
        <h3 style="margin: 0; color: #0f172a;">HUDSON REPUESTOS</h3>
        <small style="color: #64748b;">Alvear 924, Concordia</small><br>
        <span style="display:inline-block; margin-top:6px; font-weight:700; color:#0284c7;">👤 {u_act['nombre']}</span><br>
        <span class="badge-admin">{'ADMINISTRACIÓN' if es_admin else 'OPERADOR MOSTRADOR'}</span>
    </div>
    <hr style="margin: 8px 0;">
    """, unsafe_allow_html=True)

    if es_admin:
        opciones = [
            "Terminal Mostrador (Punto de Venta)",
            "Arqueo y Cierre de Caja",
            "Tablero Gerencial de Control",
            "Ajuste Masivo de Precios (Inflación)",
            "Stock Crítico y Reposición",
            "Ventas y Facturación Histórica",
            "Inventario, Precios & Importador Excel",
            "Cartera de Clientes & Cuentas Corrientes",
            "Pedidos a Proveedores (WhatsApp)",
            "Logística Territorial (Concordia)",
            "Usuarios y Accesos"
        ]
    else:
        # ARQUEO DE CAJA RETIRADO PARA EL USUARIO DE CAJA / MOSTRADOR
        opciones = [
            "Terminal Mostrador (Punto de Venta)",
            "Inventario, Precios & Importador Excel"
        ]

    menu = st.radio("Módulos", opciones, label_visibility="collapsed")
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔒 Cerrar Sesión", use_container_width=True):
        st.session_state["user"] = None
        st.session_state["cart"] = []
        st.rerun()

# ========================================================
# MÓDULO 1: TERMINAL MOSTRADOR RÁPIDA (CON TICKET & WHATSAPP)
# ========================================================
if menu == "Terminal Mostrador (Punto de Venta)":
    st.markdown('<div class="main-title">Punto de Venta Mostrador</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Venta rápida de piezas, carrito multiproducto y calculadora instantánea de vuelto</div>', unsafe_allow_html=True)

    col_izq, col_der = st.columns([1.25, 1])

    with col_izq:
        st.subheader("1. Buscar repuesto para el carrito")
        reps = session.query(Repuesto).all()
        rep_map = {f"{r.codigo} - {r.descripcion} ({fmt(r.precio_venta)} | Stock: {r.stock or 0})": r for r in reps}
        if rep_map:
            sel_rep_str = st.selectbox("Seleccione o busque pieza:", list(rep_map.keys()))
            rep_sel = rep_map[sel_rep_str]

            ci1, ci2, ci3 = st.columns(3)
            ci1.info(f"📍 Estantería: **{rep_sel.ubicacion or 'Mostrador'}**")
            ci2.info(f"🏷️ Marca: **{rep_sel.marca or 'Alternativo'}**")
            ci3.metric("Stock en Local", f"{rep_sel.stock or 0} u.")

            ca1, ca2 = st.columns([1, 2])
            stock_max = max(1, rep_sel.stock if rep_sel.stock is not None else 0)
            cant_vender = ca1.number_input("Cantidad", min_value=1, max_value=stock_max, value=1)
            if ca2.button("➕ Sumar a la Orden", use_container_width=True):
                p_costo = float(rep_sel.costo or 0.0)
                p_venta = float(rep_sel.precio_venta or 0.0)
                st.session_state["cart"].append({
                    "id": rep_sel.id,
                    "codigo": rep_sel.codigo,
                    "desc": rep_sel.descripcion,
                    "costo": p_costo,
                    "precio": p_venta,
                    "cant": cant_vender,
                    "subtotal": p_venta * cant_vender
                })
                st.toast("Repuesto sumado a la orden.")
        else:
            st.warning("No hay repuestos en el inventario.")

        st.markdown("---")
        st.subheader("🛒 Resumen de la Orden Actual")
        if st.session_state["cart"]:
            df_cart = pd.DataFrame(st.session_state["cart"])[["codigo", "desc", "cant", "precio", "subtotal"]]
            df_cart.columns = ["Código", "Descripción", "Cant.", "Precio Unit.", "Subtotal ($)"]
            df_cart["Precio Unit."] = df_cart["Precio Unit."].apply(fmt)
            df_cart["Subtotal ($)"] = df_cart["Subtotal ($)"].apply(fmt)
            st.dataframe(df_cart, use_container_width=True, hide_index=True)

            if st.button("🗑️ Vaciar Orden"):
                st.session_state["cart"] = []
                st.rerun()
        else:
            st.info("La orden está vacía. Seleccione repuestos arriba para cobrar.")

    with col_der:
        st.subheader("2. Cobro & Vuelto")
        subtotal_orden = sum(item["subtotal"] for item in st.session_state["cart"])
        costo_orden = sum(item["costo"] * item["cant"] for item in st.session_state["cart"])

        descuento_pct = st.selectbox("Bonificación / Descuento Gremio:", [0, 5, 10, 15, 20], format_func=lambda x: f"{x}% Bonificación" if x > 0 else "Sin Descuento (Precio Lista)")
        monto_descuento = subtotal_orden * (descuento_pct / 100.0)
        total_a_cobrar = subtotal_orden - monto_descuento

        st.markdown(f"""
        <div style="background-color: #1e293b; padding: 18px; border-radius: 10px; border: 2px solid #38bdf8; text-align: center;">
            <div style="font-size: 0.85rem; color: #94a3b8; font-weight:700;">TOTAL NETO A COBRAR</div>
            <div style="font-size: 3rem; font-weight: 900; color: #38bdf8;">{fmt(total_a_cobrar)}</div>
            {"<div style='color:#ef4444; font-size:0.85rem;'>Descuento aplicado: -" + fmt(monto_descuento) + "</div>" if descuento_pct > 0 else ""}
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        medio_pago = st.selectbox("Medio de Pago", ["Efectivo", "Débito / Tarjeta", "Transferencia / QR", "Cuenta Corriente"])

        clis = session.query(Cliente).all()
        clis_dict = {"Consumidor Final (Mostrador)": None}
        for c in clis:
            clis_dict[f"{c.nombre} (Saldo CC: {fmt(c.saldo_cuenta_corriente)})"] = c

        cliente_sel_str = st.selectbox("Cliente / Taller", list(clis_dict.keys()))
        cliente_sel_obj = clis_dict[cliente_sel_str]

        if cliente_sel_obj and (cliente_sel_obj.vehiculo or cliente_sel_obj.numero_motor or cliente_sel_obj.numero_chasis):
            st.markdown(f"""
            <div class="ficha-auto">
                🚗 <b>Vehículo:</b> {cliente_sel_obj.vehiculo or 'No especificado'}<br>
                ⚙️ <b>N° Motor:</b> {cliente_sel_obj.numero_motor or 'No registrado'}<br>
                🔍 <b>N° Chasis/VIN:</b> {cliente_sel_obj.numero_chasis or 'No registrado'}
            </div>
            """, unsafe_allow_html=True)

        pago_cliente = 0.0
        vuelto = 0.0

        if medio_pago == "Efectivo" and total_a_cobrar > 0:
            st.markdown("#### 💵 Calculadora de Vuelto")
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("+$10.000"):
                st.session_state["billete_extra"] += 10000
            if b2.button("+$20.000"):
                st.session_state["billete_extra"] += 20000
            if b3.button("+$50.000"):
                st.session_state["billete_extra"] += 50000
            if b4.button("Resetear"):
                st.session_state["billete_extra"] = 0.0

            pago_sugerido = float(total_a_cobrar + st.session_state["billete_extra"])
            pago_cliente = st.number_input("¿Con cuánto abona el cliente? ($)", min_value=0.0, step=1000.0, value=pago_sugerido)
            vuelto = max(0.0, pago_cliente - total_a_cobrar)

            st.markdown(f'''
            <div class="vuelto-banner">
                <div style="font-size: 0.85rem; letter-spacing: 1px; font-weight:700;">VUELTO EXACTO A ENTREGAR</div>
                <div class="vuelto-txt">{fmt(vuelto)}</div>
            </div>
            ''', unsafe_allow_html=True)

        if st.session_state["cart"]:
            if medio_pago == "Efectivo" and pago_cliente < total_a_cobrar:
                st.warning("⚠️ El monto abonado no puede ser inferior al total a cobrar.")
            else:
                if st.button("✅ Registrar Venta y Descontar Stock", type="primary", use_container_width=True):
                    items_comprados = list(st.session_state["cart"])
                    detalle_txt = "\n".join([f"{it['cant']}x {it['desc']} ({it['codigo']}) - Sub: {fmt(it['subtotal'])}" for it in items_comprados])
                    
                    nuevo_pedido = Pedido(
                        cliente_id=cliente_sel_obj.id if cliente_sel_obj else None,
                        detalle=detalle_txt,
                        canal="Mostrador / Local",
                        estado="Entregado",
                        costo_total=costo_orden,
                        precio_total=total_a_cobrar,
                        metodo_pago=medio_pago,
                        monto_abonado=pago_cliente if medio_pago == "Efectivo" else total_a_cobrar,
                        vuelto=vuelto if medio_pago == "Efectivo" else 0.0
                    )
                    session.add(nuevo_pedido)

                    for it in items_comprados:
                        r_db = session.query(Repuesto).get(it["id"])
                        if r_db:
                            stk_prev = r_db.stock if r_db.stock is not None else 0
                            r_db.stock = max(0, stk_prev - it["cant"])

                    if medio_pago == "Cuenta Corriente" and cliente_sel_obj:
                        cliente_sel_obj.saldo_cuenta_corriente += total_a_cobrar
                    else:
                        session.add(MovimientoCaja(
                            tipo="INGRESO_VENTA",
                            concepto=f"Venta Mostrador Orden #{nuevo_pedido.id}",
                            medio=medio_pago,
                            monto=total_a_cobrar,
                            usuario=u_act["username"]
                        ))

                    session.commit()

                    st.session_state["ultima_venta"] = {
                        "id": nuevo_pedido.id,
                        "cliente_nom": cliente_sel_str.split(" (")[0],
                        "cliente_tel": cliente_sel_obj.telefono if cliente_sel_obj else "",
                        "items": items_comprados,
                        "total": total_a_cobrar,
                        "medio": medio_pago,
                        "abono": pago_cliente,
                        "vuelto": vuelto
                    }

                    st.session_state["cart"] = []
                    st.session_state["billete_extra"] = 0.0
                    st.success(f"¡Venta concretada exitosamente! Vuelto entregado: {fmt(vuelto)}")

        if st.session_state.get("ultima_venta"):
            uv = st.session_state["ultima_venta"]
            st.markdown("---")
            st.markdown(f"#### 📄 Comprobante Venta #{uv['id']}")
            
            c_pdf, c_wa = st.columns(2)
            with c_pdf:
                pdf_bytes = generar_ticket_pdf(
                    uv["id"],
                    datetime.utcnow(),
                    uv["cliente_nom"],
                    uv["items"],
                    uv["total"],
                    uv["medio"],
                    uv["abono"],
                    uv["vuelto"]
                )
                st.download_button("🖨️ Descargar Ticket PDF", data=pdf_bytes, file_name=f"Ticket_{uv['id']}.pdf", mime="application/pdf", use_container_width=True)

            with c_wa:
                tel_para_wa = st.text_input("WhatsApp Cliente (con código de área):", value=uv["cliente_tel"] or "", placeholder="Ej: 3454123456")
                lineas_art = "\n".join([f"• {it['cant']}x {it['desc']} ({fmt(it['subtotal'])})" for it in uv["items"]])
                msg_ticket = (
                    f"¡Hola {uv['cliente_nom']}! 👋\n"
                    f"Gracias por tu compra en *Hudson Repuestos* (Concordia).\n\n"
                    f"*Detalle de compra #{uv['id']}:*\n{lineas_art}\n\n"
                    f"*Total:* {fmt(uv['total'])}\n"
                    f"*Forma de pago:* {uv['medio']}\n\n"
                    f"📍 Alvear 924, Concordia • Tel: 3454-XXXXXX"
                )
                if tel_para_wa:
                    tel_clean = limpiar_telefono(tel_para_wa)
                    link_wa_ticket = f"https://wa.me/{tel_clean}?text={urllib.parse.quote(msg_ticket)}"
                    st.link_button("📲 Enviar Ticket por WhatsApp", link_wa_ticket, use_container_width=True)

# ========================================================
# MÓDULO 2: ARQUEO Y CIERRE DE CAJA DIARIO (SOLO ADMIN)
# ========================================================
elif menu == "Arqueo y Cierre de Caja" and es_admin:
    st.markdown('<div class="main-title">Control y Arqueo Diario de Caja</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Auditoría de efectivo físico, discriminación por medios de cobro y cierre ciego de turno</div>', unsafe_allow_html=True)

    t_bal, t_egr = st.tabs(["📊 Arqueo y Conciliación", "➕ Registrar Movimiento Manual (Apertura / Egreso)"])

    movs = session.query(MovimientoCaja).all()
    ef_ingresos = sum(m.monto for m in movs if m.medio == "Efectivo" and m.tipo in ["INGRESO_VENTA", "APERTURA", "COBRO_CC"])
    ef_egresos = sum(m.monto for m in movs if m.medio == "Efectivo" and m.tipo == "EGRESO")
    ef_teorico = ef_ingresos - ef_egresos

    tarjeta_total = sum(m.monto for m in movs if "Tarjeta" in m.medio or "Débito" in m.medio)
    transf_total = sum(m.monto for m in movs if "Transferencia" in m.medio or "QR" in m.medio)

    with t_bal:
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f'<div class="kpi-card"><div class="kpi-title">Efectivo en Cajón (Esperado)</div><div class="kpi-value">{fmt(ef_teorico)}</div></div>', unsafe_allow_html=True)
        k2.markdown(f'<div class="kpi-card"><div class="kpi-title">Ventas en Tarjeta / Débito</div><div class="kpi-value">{fmt(tarjeta_total)}</div></div>', unsafe_allow_html=True)
        k3.markdown(f'<div class="kpi-card"><div class="kpi-title">Transferencias / QR</div><div class="kpi-value">{fmt(transf_total)}</div></div>', unsafe_allow_html=True)
        k4.markdown(f'<div class="kpi-card"><div class="kpi-title">Total Ingresado en el Turno</div><div class="kpi-value">{fmt(ef_ingresos + tarjeta_total + transf_total)}</div></div>', unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("Cierre Ciego de Turno (Auditoría)")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            conteo_cajero = st.number_input("Dinero físico contado por el cajero ($):", min_value=0.0, step=1000.0)
            if conteo_cajero > 0:
                diferencia = conteo_cajero - ef_teorico
                if diferencia == 0:
                    st.success("🟢 CAJA PERFECTA: El efectivo físico coincide con el sistema.")
                elif diferencia > 0:
                    st.warning(f"🟡 SOBRANTE DE CAJA: Sobran {fmt(diferencia)}")
                else:
                    st.error(f"🔴 FALTANTE DE CAJA: Faltan {fmt(abs(diferencia))}")

        with col_c2:
            st.markdown("#### Movimientos Asentados en el Libro de Caja")
            if movs:
                df_caja = pd.DataFrame([
                    {
                        "Hora": m.fecha.strftime("%H:%M"),
                        "Tipo": m.tipo,
                        "Concepto": m.concepto,
                        "Medio": m.medio,
                        "Monto": fmt(m.monto),
                        "Operador": m.usuario
                    } for m in reversed(movs)
                ])
                st.dataframe(df_caja, use_container_width=True, hide_index=True)

    with t_egr:
        with st.form("f_mov_caja"):
            tipo_mov = st.selectbox("Tipo de Movimiento", ["EGRESO (Pago de Flete, Limpieza, Retiro de Ganancia)", "APERTURA (Fondo de Cambio Inicial)", "COBRO_CC (Cliente viene a pagar cuenta corriente)"])
            monto_mov = st.number_input("Monto en Efectivo ($)", min_value=1.0, step=500.0)
            concepto_mov = st.text_input("Concepto / Motivo", placeholder="Ej: Pago a comisionista de Chajarí, Fondo para cambio...")
            if st.form_submit_button("Asentar Movimiento en Caja", use_container_width=True):
                tipo_final = "EGRESO" if "EGRESO" in tipo_mov else ("APERTURA" if "APERTURA" in tipo_mov else "COBRO_CC")
                session.add(MovimientoCaja(
                    tipo=tipo_final,
                    concepto=concepto_mov,
                    medio="Efectivo",
                    monto=monto_mov,
                    usuario=u_act["username"]
                ))
                session.commit()
                st.success("Movimiento registrado en caja.")
                st.rerun()

# ========================================================
# MÓDULO 3: TABLERO GERENCIAL DE CONTROL (KPIs)
# ========================================================
elif menu == "Tablero Gerencial de Control" and es_admin:
    st.markdown('<div class="main-title">Tablero de Control Gerencial</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Indicadores económicos, rentabilidad y valorización de inventario</div>', unsafe_allow_html=True)

    pedidos = session.query(Pedido).all()
    facturacion = sum(p.precio_total for p in pedidos)
    costo_mercaderia = sum(p.costo_total for p in pedidos)
    ganancia_bruta = facturacion - costo_mercaderia
    margen_pct = (ganancia_bruta / facturacion * 100) if facturacion > 0 else 0.0

    reps = session.query(Repuesto).all()
    capital_inmovilizado = sum((r.costo or 0.0) * (r.stock or 0) for r in reps)
    total_deuda_cc = sum(c.saldo_cuenta_corriente for c in session.query(Cliente).all())

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f'<div class="kpi-card"><div class="kpi-title">Facturación Neta</div><div class="kpi-value">{fmt(facturacion)}</div></div>', unsafe_allow_html=True)
    k2.markdown(f'<div class="kpi-card"><div class="kpi-title">Ganancia Bruta</div><div class="kpi-value">{fmt(ganancia_bruta)}</div><small style="color:#22c55e;">Margen: {margen_pct:.1f}%</small></div>', unsafe_allow_html=True)
    k3.markdown(f'<div class="kpi-card"><div class="kpi-title">Capital en Stock (Costo)</div><div class="kpi-value">{fmt(capital_inmovilizado)}</div></div>', unsafe_allow_html=True)
    k4.markdown(f'<div class="kpi-card"><div class="kpi-title">Crédito en Calle (CC)</div><div class="kpi-value">{fmt(total_deuda_cc)}</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Ventas por Método de Pago")
    if pedidos:
        df_p = pd.DataFrame([{"Monto": p.precio_total, "Medio": p.metodo_pago} for p in pedidos])
        fig_pie = px.pie(df_p, values="Monto", names="Medio", hole=0.4, template="plotly_dark")
        st.plotly_chart(fig_pie, use_container_width=True)

# ========================================================
# MÓDULO 4: AJUSTE MASIVO DE PRECIOS POR INFLACIÓN
# ========================================================
elif menu == "Ajuste Masivo de Precios (Inflación)" and es_admin:
    st.markdown('<div class="main-title">Ajuste Masivo de Precios & Dólar</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Herramienta para trasladar aumentos de proveedores o inflación en 1 click</div>', unsafe_allow_html=True)

    col_aj1, col_aj2 = st.columns(2)
    with col_aj1:
        st.subheader("Aumento por Rubro o Marca")
        rubros = list(set(r.rubro for r in session.query(Repuesto).all() if r.rubro))
        rubro_sel = st.selectbox("Seleccione Rubro a Actualizar", ["TODOS LOS RUBROS"] + rubros)

        marcas = list(set(r.marca for r in session.query(Repuesto).all() if r.marca))
        marca_sel = st.selectbox("Filtrar por Marca", ["TODAS LAS MARCAS"] + marcas)

        pct_aumento = st.number_input("Porcentaje de Aumento (%)", min_value=-50.0, max_value=100.0, value=7.5, step=0.5)

        if st.button("🚀 Aplicar Aumento Masivo de Precios", type="primary", use_container_width=True):
            query = session.query(Repuesto)
            if rubro_sel != "TODOS LOS RUBROS":
                query = query.filter(Repuesto.rubro == rubro_sel)
            if marca_sel != "TODAS LAS MARCAS":
                query = query.filter(Repuesto.marca == marca_sel)
            
            piezas_afectadas = query.all()
            for r in piezas_afectadas:
                p_v = float(r.precio_venta or 0.0)
                p_c = float(r.costo or 0.0)
                r.precio_venta = round(p_v * (1 + pct_aumento / 100.0), -1)
                r.costo = round(p_c * (1 + pct_aumento / 100.0), -1)

            session.commit()
            st.success(f"¡Se actualizaron {len(piezas_afectadas)} repuestos con un {pct_aumento}% de incremento!")
            st.rerun()

    with col_aj2:
        st.info("💡 **Consejo:** Trasladá en segundos aumentos de listas mayoristas a todo el inventario sin editar artículo por artículo.")

# ========================================================
# MÓDULO 5: STOCK CRÍTICO Y REPOSICIÓN INTELIGENTE
# ========================================================
elif menu == "Stock Crítico y Reposición" and es_admin:
    st.markdown('<div class="main-title">Control de Quiebre de Stock</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Piezas que alcanzaron el stock mínimo de seguridad y requieren reposición</div>', unsafe_allow_html=True)

    reps_criticos = session.query(Repuesto).filter(Repuesto.stock <= Repuesto.stock_minimo).all()
    if reps_criticos:
        df_crit = pd.DataFrame([
            {
                "Código": r.codigo,
                "Descripción": r.descripcion,
                "Marca": r.marca,
                "Stock Actual": r.stock or 0,
                "Stock Mínimo": r.stock_minimo or 0,
                "Sugerido a Pedir": max(1, ((r.stock_minimo or 2) * 2) - (r.stock or 0)),
                "Costo Estimado Unit.": fmt(r.costo)
            } for r in reps_criticos
        ])
        st.dataframe(df_crit, use_container_width=True, hide_index=True)

        pedido_auto = "\n".join([f"- {max(1, ((r.stock_minimo or 2)*2)-(r.stock or 0))}x {r.descripcion} ({r.codigo}) [{r.marca}]" for r in reps_criticos])
        msg_auto = f"Hola! Te paso el pedido de reposición urgente para Hudson Repuestos:\n\n{pedido_auto}"
        st.text_area("Borrador generado para el distribuidor:", value=msg_auto, height=120)
    else:
        st.success("🟢 Todos los repuestos tienen niveles óptimos de stock. No hay quiebres de inventario.")

# ========================================================
# MÓDULO 6: HISTORIAL DE VENTAS
# ========================================================
elif menu == "Ventas y Facturación Histórica" and es_admin:
    st.markdown('<div class="main-title">Registro Histórico de Ventas</div>', unsafe_allow_html=True)
    pedidos = session.query(Pedido).order_by(Pedido.fecha.desc()).all()
    if pedidos:
        df_p = pd.DataFrame([
            {
                "N°": p.id,
                "Fecha": p.fecha.strftime("%d/%m/%Y %H:%M"),
                "Cliente": p.cliente.nombre if p.cliente else "Consumidor Final",
                "Detalle": p.detalle,
                "Total Cobrado": fmt(p.precio_total),
                "Medio": p.metodo_pago,
                "Vuelto": fmt(p.vuelto)
            } for p in pedidos
        ])
        st.dataframe(df_p, use_container_width=True, hide_index=True)
    else:
        st.info("Sin registros de ventas.")

# ========================================================
# MÓDULO 7: INVENTARIO, PRECIOS, IMPORTADOR & BORRADO MASIVO
# ========================================================
elif menu == "Inventario, Precios & Importador Excel":
    st.markdown('<div class="main-title">Inventario & Catálogo de Autopartes</div>', unsafe_allow_html=True)
    
    if es_admin:
        pestanas = ["📦 Catálogo Activo", "📥 Importar Excel / CSV", "➕ Cargar Repuesto Manual", "🗑️ Eliminar Repuesto", "⚠️ Vaciar Inventario Completo"]
    else:
        pestanas = ["📦 Catálogo Activo", "📥 Importar Excel / CSV", "➕ Cargar Repuesto Manual"]

    tabs_inv = st.tabs(pestanas)
    t_list = tabs_inv[0]
    t_import = tabs_inv[1]
    t_alta = tabs_inv[2]
    t_delete = tabs_inv[3] if es_admin else None
    t_wipe = tabs_inv[4] if es_admin else None

    with t_list:
        reps = session.query(Repuesto).all()
        if reps:
            df_r = pd.DataFrame([
                {
                    "Código": r.codigo,
                    "Descripción": r.descripcion,
                    "Marca": r.marca,
                    "Rubro": r.rubro,
                    "Stock": r.stock or 0,
                    "Ubicación": r.ubicacion or "Mostrador",
                    "Costo": fmt(r.costo),
                    "Precio Venta": fmt(r.precio_venta),
                } for r in reps
            ])
            st.dataframe(df_r, use_container_width=True, hide_index=True)
        else:
            st.info("No hay repuestos en el catálogo actualmente.")

    with t_import:
        st.subheader("Cargar Lista de Precios de Distribuidor")
        st.markdown("Subí el archivo de **Excel (.xlsx, .xls)** o **CSV** que te manda el fabricante o distribuidora.")
        archivo = st.file_uploader("Seleccionar archivo de lista de precios", type=["xlsx", "xls", "csv"])

        if archivo is not None:
            try:
                if archivo.name.endswith(".csv"):
                    df_up = pd.read_csv(archivo)
                else:
                    df_up = pd.read_excel(archivo)

                st.success(f"Archivo cargado con éxito. Se detectaron **{len(df_up)} filas**.")
                st.write("Vista previa:")
                st.dataframe(df_up.head(4), use_container_width=True)

                st.markdown("---")
                cols = list(df_up.columns)
                c_m1, c_m2, c_m3 = st.columns(3)
                col_cod = c_m1.selectbox("Columna con el CÓDIGO de pieza:", cols)
                col_desc = c_m2.selectbox("Columna con la DESCRIPCIÓN:", cols)
                col_costo = c_m3.selectbox("Columna con el PRECIO / COSTO:", cols)

                c_m4, c_m5 = st.columns(2)
                marca_defecto = c_m4.text_input("Marca de esta lista:", value="Distribuidor Oficial")
                rubro_defecto = c_m5.selectbox("Rubro general:", ["Frenos y Suspensión", "Motor", "Filtros y Aceites", "Transmisión", "Electricidad", "Accesorios"])

                margen_ganancia = st.slider("Si la columna es el COSTO de compra, ¿qué % de ganancia querés sumarle para fijar el precio de venta?", min_value=0, max_value=150, value=40, step=5)

                if st.button("⚡ Procesar e Impactar Precios en el Sistema", type="primary", use_container_width=True):
                    actualizados = 0
                    creados = 0

                    for _, row in df_up.iterrows():
                        raw_cod = str(row[col_cod]).strip()
                        raw_desc = str(row[col_desc]).strip()
                        try:
                            val_str = str(row[col_costo]).replace("$", "").replace(".", "").replace(",", ".").strip()
                            raw_val = float(val_str)
                        except:
                            raw_val = 0.0

                        if not raw_cod or raw_cod.lower() == "nan":
                            continue

                        p_costo = raw_val
                        p_venta = round(p_costo * (1 + margen_ganancia / 100.0), -1)

                        r_existente = session.query(Repuesto).filter(Repuesto.codigo == raw_cod).first()
                        if r_existente:
                            r_existente.costo = p_costo
                            r_existente.precio_venta = p_venta
                            r_existente.descripcion = raw_desc
                            r_existente.marca = marca_defecto
                            actualizados += 1
                        else:
                            nuevo_r = Repuesto(
                                codigo=raw_cod,
                                descripcion=raw_desc,
                                marca=marca_defecto,
                                rubro=rubro_defecto,
                                costo=p_costo,
                                precio_venta=p_venta,
                                stock=5,
                                ubicacion="Depósito"
                            )
                            session.add(nuevo_r)
                            creados += 1

                    session.commit()
                    st.success(f"¡Proceso finalizado! Repuestos actualizados: **{actualizados}** | Creados: **{creados}**.")
                    st.rerun()

            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")

    with t_alta:
        with st.form("f_nuevo_rep"):
            c1, c2 = st.columns(2)
            cod = c1.text_input("Código de Pieza *")
            des = c2.text_input("Descripción del Repuesto *")
            c3, c4 = st.columns(2)
            mar = c3.text_input("Marca", value="Alternativo")
            rub = c4.selectbox("Rubro", ["Frenos y Suspensión", "Motor", "Filtros y Aceites", "Transmisión", "Electricidad", "Accesorios"])
            c5, c6 = st.columns(2)
            cos = c5.number_input("Costo de Compra ($)", min_value=0.0)
            pre = c6.number_input("Precio de Venta ($)", min_value=0.0)
            c7, c8 = st.columns(2)
            stk = c7.number_input("Stock Inicial", min_value=0, value=5)
            ubi = c8.text_input("Ubicación en Estantería", value="Estantería 1")
            if st.form_submit_button("Guardar Repuesto en Inventario", use_container_width=True):
                if cod and des:
                    session.add(Repuesto(codigo=cod, descripcion=des, marca=mar, rubro=rub, costo=cos, precio_venta=pre, stock=stk, ubicacion=ubi))
                    session.commit()
                    st.success("Repuesto guardado con éxito.")
                    st.rerun()

    if es_admin and t_delete:
        with t_delete:
            st.subheader("Baja Individual de Repuesto")
            reps_all = session.query(Repuesto).all()
            if reps_all:
                del_dict = {f"{r.codigo} - {r.descripcion} ({r.marca}) [Stock: {r.stock or 0}]": r for r in reps_all}
                sel_to_del_str = st.selectbox("Seleccione el repuesto a eliminar:", list(del_dict.keys()), key="sb_delete_rep")
                rep_a_borrar = del_dict[sel_to_del_str]

                st.markdown(f"""
                <div class="danger-card">
                    <b>⚠️ Datos del artículo a dar de baja:</b><br>
                    • <b>Código:</b> {rep_a_borrar.codigo}<br>
                    • <b>Descripción:</b> {rep_a_borrar.descripcion}<br>
                    • <b>Marca:</b> {rep_a_borrar.marca}<br>
                    • <b>Stock a descartar:</b> {rep_a_borrar.stock or 0} unidades<br>
                    • <b>Precio actual:</b> {fmt(rep_a_borrar.precio_venta)}
                </div>
                """, unsafe_allow_html=True)

                confirmar_check = st.checkbox(f"Confirmo que deseo dar de baja '{rep_a_borrar.codigo}' permanentemente.")
                if st.button("🗑️ Eliminar Repuesto del Sistema", type="primary", use_container_width=True):
                    if confirmar_check:
                        session.delete(rep_a_borrar)
                        session.commit()
                        st.success(f"El repuesto '{rep_a_borrar.codigo}' fue eliminado exitosamente.")
                        st.rerun()
                    else:
                        st.warning("Debe marcar la casilla de confirmación para poder proceder.")
            else:
                st.info("No hay repuestos registrados para eliminar.")

    if es_admin and t_wipe:
        with t_wipe:
            st.subheader("⚠️ Vaciado Masivo de Inventario (Solo Administrador)")
            st.markdown("""
            Esta opción elimina **absolutamente todos los repuestos** cargados en la base de datos para comenzar un inventario limpio desde cero (por ejemplo, antes de importar una lista completa nueva).
            """)
            st.markdown("""
            <div class="danger-card">
                <b>🚨 ADVERTENCIA CRÍTICA:</b><br>
                Esta acción es irreversible y vaciará todo el catálogo actual de autopartes.
            </div>
            """, unsafe_allow_html=True)

            check_wipe = st.checkbox("Entiendo los riesgos y deseo eliminar todo el catálogo de repuestos.")
            palabra_seguridad = st.text_input("Para confirmar la eliminación, escriba la palabra 'ELIMINAR':")

            if st.button("💣 Borrar Todo el Inventario", type="primary", use_container_width=True):
                if check_wipe and palabra_seguridad.strip() == "ELIMINAR":
                    session.query(Repuesto).delete()
                    session.commit()
                    st.success("¡El inventario ha sido vaciado por completo con éxito!")
                    st.rerun()
                else:
                    st.error("Debe tildar la confirmación y escribir exactamente 'ELIMINAR'.")

# ========================================================
# MÓDULO 8: CARTERA DE CLIENTES (GESTIÓN TOTAL CON SEGURIDAD)
# ========================================================
elif menu == "Cartera de Clientes & Cuentas Corrientes" and es_admin:
    st.markdown('<div class="main-title">Cartera de Clientes & Cuentas Corrientes</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Control integral de clientes, fichas de vehículos, cobranzas y administración segura</div>', unsafe_allow_html=True)

    t_cl1, t_cl2, t_cl3, t_cl4, t_cl5 = st.tabs([
        "👥 Cuentas Corrientes & Fichas",
        "✏️ Modificar Cliente",
        "🗑️ Eliminar Cliente",
        "📲 Recordatorio WhatsApp",
        "➕ Nuevo Cliente"
    ])

    with t_cl1:
        clis = session.query(Cliente).all()
        if clis:
            df_c = pd.DataFrame([
                {
                    "ID": c.id,
                    "Nombre / Taller": c.nombre,
                    "Tipo": c.tipo,
                    "Teléfono": c.telefono or "-",
                    "Vehículo / Modelo": c.vehiculo or "-",
                    "N° Motor": c.numero_motor or "-",
                    "N° Chasis": c.numero_chasis or "-",
                    "Dirección": c.direccion or "-",
                    "Deuda en CC ($)": fmt(c.saldo_cuenta_corriente)
                } for c in clis
            ])
            st.dataframe(df_c, use_container_width=True, hide_index=True)
        else:
            st.info("No hay clientes registrados en la cartera.")

    with t_cl2:
        st.subheader("Modificar Datos de Cliente Existente")
        clis_all = session.query(Cliente).all()
        if clis_all:
            edit_dict = {f"#{c.id} - {c.nombre} ({c.tipo})": c for c in clis_all}
            sel_edit_str = st.selectbox("Seleccione el cliente que desea editar:", list(edit_dict.keys()), key="sb_edit_cli")
            c_edit = edit_dict[sel_edit_str]

            with st.form(f"f_edit_cli_{c_edit.id}"):
                st.markdown(f"**Modificando ficha de: {c_edit.nombre} (ID #{c_edit.id})**")
                e1, e2 = st.columns(2)
                e_nom = e1.text_input("Razón Social / Nombre", value=c_edit.nombre or "")
                tipos_posibles = ["Taller Mecánico", "Lubricentro", "Particular", "Flotista"]
                idx_tipo = tipos_posibles.index(c_edit.tipo) if c_edit.tipo in tipos_posibles else 0
                e_tip = e2.selectbox("Tipo de Cliente", tipos_posibles, index=idx_tipo)

                e3, e4 = st.columns(2)
                e_tel = e3.text_input("Teléfono / WhatsApp", value=c_edit.telefono or "")
                e_dir = e4.text_input("Dirección", value=c_edit.direccion or "Concordia, Entre Ríos")

                st.markdown("##### Ficha Técnica del Vehículo")
                ev1, ev2, ev3 = st.columns(3)
                e_veh = ev1.text_input("Vehículo / Modelo", value=c_edit.vehiculo or "")
                e_mot = ev2.text_input("N° Motor", value=c_edit.numero_motor or "")
                e_cha = ev3.text_input("N° Chasis / VIN", value=c_edit.numero_chasis or "")

                st.markdown("##### Saldo de Cuenta Corriente")
                e_saldo = st.number_input("Saldo adeudado ($):", min_value=0.0, step=1000.0, value=float(c_edit.saldo_cuenta_corriente or 0.0))

                if st.form_submit_button("💾 Guardar Cambios", type="primary", use_container_width=True):
                    c_edit.nombre = e_nom.strip()
                    c_edit.tipo = e_tip
                    c_edit.telefono = e_tel.strip()
                    c_edit.direccion = e_dir.strip()
                    c_edit.vehiculo = e_veh.strip()
                    c_edit.numero_motor = e_mot.strip()
                    c_edit.numero_chasis = e_cha.strip()
                    c_edit.saldo_cuenta_corriente = e_saldo
                    session.commit()
                    st.success(f"¡Ficha de '{c_edit.nombre}' actualizada exitosamente!")
                    st.rerun()
        else:
            st.info("No hay clientes para modificar.")

    with t_cl3:
        st.subheader("Baja Definitiva de Cliente")
        st.markdown("Elimina un cliente duplicado o cargado por error. Los pedidos históricos quedarán preservados.")
        clis_all_del = session.query(Cliente).all()
        if clis_all_del:
            del_dict = {f"#{c.id} - {c.nombre} (Deuda: {fmt(c.saldo_cuenta_corriente)}) [Tel: {c.telefono or 'S/T'}]": c for c in clis_all_del}
            sel_del_str = st.selectbox("Seleccione el cliente a eliminar:", list(del_dict.keys()), key="sb_del_cli")
            c_del = del_dict[sel_del_str]

            deuda_val = float(c_del.saldo_cuenta_corriente or 0.0)
            if deuda_val > 0:
                st.markdown(f"""
                <div class="danger-card">
                    ⚠️ <b>¡ATENCIÓN! CLIENTE CON DEUDA PENDIENTE:</b><br>
                    Este cliente posee un saldo deudor en cuenta corriente de <b>{fmt(deuda_val)}</b>.<br>
                    Si lo elimina, se borrará el registro de esa deuda de su cartera de clientes.
                </div>
                """, unsafe_allow_html=True)

            st.markdown(f"""
            <div style="background-color: #1e293b; padding: 14px; border-radius: 8px; border: 1px solid #475569; margin-bottom: 15px;">
                <b>Ficha seleccionada para baja:</b><br>
                • <b>ID:</b> #{c_del.id} | <b>Nombre:</b> {c_del.nombre}<br>
                • <b>Tipo:</b> {c_del.tipo} | <b>Tel:</b> {c_del.telefono or 'No registrado'}<br>
                • <b>Vehículo:</b> {c_del.vehiculo or 'Sin datos'}<br>
                • <b>Saldo actual:</b> {fmt(deuda_val)}
            </div>
            """, unsafe_allow_html=True)

            conf_borrar = st.checkbox(f"Confirmo expresamente que deseo eliminar a '{c_del.nombre}' (ID #{c_del.id}) de la base de datos.")

            if st.button("🗑️ Eliminar Cliente Definitivamente", type="primary", use_container_width=True):
                if conf_borrar:
                    session.delete(c_del)
                    session.commit()
                    st.success(f"Cliente #{c_del.id} eliminado con éxito.")
                    st.rerun()
                else:
                    st.warning("Debe marcar la casilla de confirmación para autorizar la eliminación.")
        else:
            st.info("No hay clientes disponibles para eliminar.")

    with t_cl4:
        st.subheader("Cobranza / Recordatorio de Cuenta Corriente por WhatsApp")
        clis_deuda = session.query(Cliente).filter(Cliente.saldo_cuenta_corriente > 0).all()
        if clis_deuda:
            map_deuda = {f"{c.nombre} (Deuda: {fmt(c.saldo_cuenta_corriente)} | Tel: {c.telefono or 'Sin teléfono'})": c for c in clis_deuda}
            c_cobrar_str = st.selectbox("Seleccione cliente a cobrar:", list(map_deuda.keys()))
            c_cobrar_obj = map_deuda[c_cobrar_str]

            tel_cobrar = st.text_input("WhatsApp de cobro:", value=c_cobrar_obj.telefono or "")
            alias_cbu = st.text_input("Alias / CBU para recibir transferencia:", value="HUDSON.REPUESTOS.BNA")

            msg_cc = (
                f"Estimado/a *{c_cobrar_obj.nombre}*, buenos días de parte de *Hudson Repuestos*.\n\n"
                f"Le informamos que el saldo pendiente en su Cuenta Corriente es de *{fmt(c_cobrar_obj.saldo_cuenta_corriente)}*.\n\n"
                f"Puede abonar mediante transferencia al siguiente Alias:\n"
                f"👉 *{alias_cbu}*\n\n"
                f"Muchas gracias por su confianza y trabajo conjunto."
            )
            st.text_area("Mensaje a enviar:", value=msg_cc, height=140)
            if tel_cobrar:
                link_cc_wa = f"https://wa.me/{limpiar_telefono(tel_cobrar)}?text={urllib.parse.quote(msg_cc)}"
                st.link_button("📲 Abrir WhatsApp y Enviar Estado de Deuda", link_cc_wa, use_container_width=True)
        else:
            st.success("🟢 Excelente: No hay clientes con saldo pendiente de cobro en cuenta corriente.")

    with t_cl5:
        with st.form("f_add_cli"):
            st.subheader("Datos de Contacto y Comerciales")
            c1, c2 = st.columns(2)
            nom = c1.text_input("Razón Social / Nombre *")
            tip = c2.selectbox("Tipo de Cliente", ["Taller Mecánico", "Lubricentro", "Particular", "Flotista"])
            
            c3, c4 = st.columns(2)
            tel = c3.text_input("Teléfono / WhatsApp (Ej: 3454123456)")
            dire = c4.text_input("Dirección (Concordia)", value="Concordia, Entre Ríos")

            st.markdown("---")
            st.subheader("Ficha del Vehículo (Opcionales)")
            st.caption("Permite enlazar el vehículo con el inventario para asegurar repuestos compatibles.")
            v1, v2, v3 = st.columns(3)
            veh = v1.text_input("Vehículo / Modelo", placeholder="Ej: Hilux 2.8 TDI / Gol Trend 1.6")
            mot = v2.text_input("Número de Motor", placeholder="Ej: 1GD-123456 (Opcional)")
            cha = v3.text_input("Número de Chasis / VIN", placeholder="Ej: 8AJBA3CD... (Opcional)")

            if st.form_submit_button("Guardar Cliente en la Cartera", use_container_width=True):
                if nom:
                    session.add(Cliente(
                        nombre=nom.strip(),
                        tipo=tip,
                        telefono=tel.strip(),
                        direccion=dire.strip(),
                        vehiculo=veh.strip(),
                        numero_motor=mot.strip(),
                        numero_chasis=cha.strip()
                    ))
                    session.commit()
                    st.success("Cliente guardado exitosamente.")
                    st.rerun()
                else:
                    st.error("El nombre o razón social es obligatorio.")

# ========================================================
# MÓDULO 9: PEDIDOS A PROVEEDORES (WHATSAPP MAYORISTA)
# ========================================================
elif menu == "Pedidos a Proveedores (WhatsApp)" and es_admin:
    st.markdown('<div class="main-title">Órdenes a Distribuidores & Proveedores</div>', unsafe_allow_html=True)
    wa_num = st.text_input("WhatsApp del Distribuidor Mayorista", placeholder="Ej: 3454123456")
    wa_txt = st.text_area("Detalle del pedido de piezas", height=120, placeholder="Ej:\n- 4x Amortiguador Hilux Corven\n- 10x Pastillas Gol Trend Fras-le")
    if wa_num and wa_txt:
        enlace_wa = f"https://wa.me/{limpiar_telefono(wa_num)}?text={urllib.parse.quote('Hola! Pedido de reposición para Hudson Repuestos (Concordia):\n\n' + wa_txt)}"
        st.link_button("📲 Enviar Orden por WhatsApp", enlace_wa)

# ========================================================
# MÓDULO 10: LOGÍSTICA TERRITORIAL (CONCORDIA)
# ========================================================
elif menu == "Logística Territorial (Concordia)" and es_admin:
    st.markdown('<div class="main-title">Logística Territorial & Talleres</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Ubicación de Casa Central Hudson Repuestos y talleres clientes en Concordia</div>', unsafe_allow_html=True)

    m = folium.Map(location=[-31.3929, -58.0209], zoom_start=13)
    folium.Marker([-31.3929, -58.0209], popup="Hudson Repuestos (Alvear 924)", tooltip="Casa Central", icon=folium.Icon(color="red", icon="home")).add_to(m)

    for c in session.query(Cliente).all():
        if c.lat and c.lon:
            folium.Marker([c.lat, c.lon], popup=f"{c.nombre} ({c.tipo}) - {c.vehiculo or 'S/V'}", tooltip=c.nombre, icon=folium.Icon(color="blue", icon="wrench")).add_to(m)

    st_folium(m, width=950, height=480)

# ========================================================
# MÓDULO 11: USUARIOS Y ACCESOS (GESTIÓN COMPLETA: ALTA Y BAJA)
# ========================================================
elif menu == "Usuarios y Accesos" and es_admin:
    st.markdown('<div class="main-title">Gestión de Usuarios y Roles de Acceso</div>', unsafe_allow_html=True)
    st.markdown('<div class="main-subtitle">Control de operadores de mostrador, directores y permisos de terminal</div>', unsafe_allow_html=True)

    t_u1, t_u2, t_u3 = st.tabs(["👥 Lista de Usuarios Activos", "➕ Registrar Nuevo Usuario", "🗑️ Eliminar / Suspender Usuario"])

    with t_u1:
        usrs = session.query(Usuario).all()
        df_u = pd.DataFrame([
            {
                "ID": u.id,
                "Nombre Completo": u.nombre,
                "Usuario": u.username,
                "Rol / Nivel": u.rol,
                "Estado": "🟢 Activo" if u.activo else "🔴 Suspendido"
            } for u in usrs
        ])
        st.dataframe(df_u, use_container_width=True, hide_index=True)

    with t_u2:
        with st.form("f_nuevo_usuario"):
            st.subheader("Alta de Nuevo Operador")
            c1, c2 = st.columns(2)
            u_nom = c1.text_input("Nombre y Apellido *")
            u_usr = c2.text_input("Nombre de Usuario (Login) *")
            c3, c4 = st.columns(2)
            u_pass = c3.text_input("Contraseña de Acceso *", type="password")
            u_rol = c4.selectbox("Rol y Permisos", ["MOSTRADOR", "ADMIN"])

            if st.form_submit_button("Guardar y Crear Usuario", type="primary", use_container_width=True):
                if u_nom and u_usr and u_pass:
                    u_usr_clean = u_usr.strip().lower()
                    if session.query(Usuario).filter(Usuario.username == u_usr_clean).first():
                        st.error("El nombre de usuario ya existe. Elija otro.")
                    else:
                        session.add(Usuario(
                            nombre=u_nom.strip(),
                            username=u_usr_clean,
                            password=u_pass.strip(),
                            rol=u_rol,
                            activo=True
                        ))
                        session.commit()
                        st.success(f"Usuario '{u_usr_clean}' creado con éxito.")
                        st.rerun()
                else:
                    st.error("Todos los campos con asterisco (*) son obligatorios.")

    with t_u3:
        st.subheader("Baja o Suspensión de Usuario")
        usrs_del = session.query(Usuario).all()
        user_actual_id = u_act.get("id")

        if usrs_del:
            map_del_u = {f"{u.nombre} (@{u.username}) - Rol: {u.rol}": u for u in usrs_del}
            sel_u_str = st.selectbox("Seleccione usuario a gestionar:", list(map_del_u.keys()))
            u_sel = map_del_u[sel_u_str]

            if u_sel.id == user_actual_id:
                st.warning("⚠️ No podés suspender ni eliminar tu propia cuenta mientras estás logueado.")
            else:
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    nuevo_estado = not u_sel.activo
                    lbl = "Reactivar Acceso" if not u_sel.activo else "Suspender Acceso"
                    if st.button(lbl, use_container_width=True):
                        u_sel.activo = nuevo_estado
                        session.commit()
                        st.success(f"Estado de {u_sel.username} modificado.")
                        st.rerun()

                with col_btn2:
                    conf_del_usr = st.checkbox(f"Confirmo eliminar definitivamente a {u_sel.username}")
                    if st.button("🗑️ Eliminar Usuario Permanentemente", type="primary", use_container_width=True):
                        if conf_del_usr:
                            session.delete(u_sel)
                            session.commit()
                            st.success(f"Usuario {u_sel.username} eliminado del sistema.")
                            st.rerun()
                        else:
                            st.warning("Marque la casilla de confirmación.")

# ========================================================
# PIE DE PÁGINA INSTITUCIONAL
# ========================================================
st.markdown("""
<div class="author-footer">
    <b>Hudson Master ERP & CRM</b> | Dirección General: <b>Tomas Hudson</b><br>
    Alvear 924, Concordia, Entre Ríos.
</div>
""", unsafe_allow_html=True)

session.close()
