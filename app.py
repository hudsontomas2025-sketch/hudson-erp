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
    rol = Column(String(30), default="ADMIN")
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
    tipo = Column(String(20))
    concepto = Column(String(150))
    medio = Column(String(50), default="Efectivo")
    monto = Column(Float, default=0.0)
    usuario = Column(String(50), default="tomas")

Base.metadata.create_all(engine)

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
if session_init.query(Cliente).count() == 0:
    session_init.add(Cliente(nombre="Taller Mecánico El Rusito", tipo="Taller Mecánico", telefono="3454112233", direccion="Urquiza 550", vehiculo="Gol Trend 1.6 MSI", numero_motor="CFZ123456", numero_chasis="8AWZZZ5UZ", lat=-31.395, lon=-58.018, saldo_cuenta_corriente=0.0))
    session_init.add(Cliente(nombre="Lubricentro Concordia", tipo="Lubricentro", telefono="3454998877", direccion="San Lorenzo 820", vehiculo="Toyota Hilux 2.8 D-4D", numero_motor="1GD889900", numero_chasis="8AJBA3CD", lat=-31.389, lon=-58.025, saldo_cuenta_corriente=45000.0))
    session_init.commit()
session_init.close()

# ========================================================
# 2. CONFIGURACIÓN VISUAL & CSS
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

/* Botón de ingreso: azul oscuro institucional con letras blancas */
div[data-testid="stFormSubmitButton"] > button {
    background-color: #0b1e59 !important;
    color: #ffffff !important;
    border: 2px solid #1e3a8a !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    border-radius: 8px !important;
    padding: 10px 24px !important;
    transition: all 0.25s ease-in-out !important;
}
div[data-testid="stFormSubmitButton"] > button:hover {
    background-color: #162f7a !important;
    color: #ffffff !important;
    border-color: #38bdf8 !important;
}
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
# 4. LOGIN (CON LOGO OFICIAL, USUARIO, CONTRASEÑA Y SIN REFERENCIAS)
# ========================================================
if st.session_state["user"] is None:
    c_logo1, c_logo2, c_logo3 = st.columns([1.5, 1, 1.5])
    with c_logo2:
        if os.path.exists("logo.jpg"):
            st.image("logo.jpg", use_container_width=True)
        elif os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.markdown("""
            <div style="text-align: center; margin-top: 15px;">
                <div style="display: inline-block; background: #0b1e59; padding: 22px 28px; border-radius: 50%; border: 3px solid #ffffff;">
                    <span style="font-size: 55px; font-weight: 900; color: white;">H</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<div class="main-title" style="text-align:center; margin-top:10px;">HUDSON REPUESTOS</div>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center; color:#94a3b8; font-size: 0.95rem;">Sistema de Gestión Integral ERP & CRM • Alvear 924, Concordia</p>', unsafe_allow_html=True)
    
    col_l1, col_l2, col_l3 = st.columns([1, 1.4, 1])
    with col_l2:
        with st.form("f_login"):
            st.markdown("<h4 style='text-align: center; color: #f8fafc; margin-bottom: 18px;'>Acceso al Sistema</h4>", unsafe_allow_html=True)
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            
            submit = st.form_submit_button("Ingresar al Sistema", use_container_width=True)
            
            if submit:
                u_clean = u.strip().lower()
                usr = session.query(Usuario).filter(Usuario.username == u_clean, Usuario.password == p.strip()).first()
                if usr:
                    if not usr.activo:
                        st.error("⚠️ Este usuario se encuentra suspendido.")
                    else:
                        st.session_state["user"] = {"id": usr.id, "nombre": usr.nombre, "rol": usr.rol, "username": usr.username}
                        st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")
    st.stop()

u_act = st.session_state["user"]
es_admin = (u_act["rol"] == "ADMIN")

# ========================================================
# 5. MENÚ LATERAL (CON LOGO OFICIAL)
# ========================================================
with st.sidebar:
    if os.path.exists("logo.jpg"):
        st.image("logo.jpg", width=120)
    elif os.path.exists("logo.png"):
        st.image("logo.png", width=120)

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
                        monto_abonado=pago_cliente if medio_pago == "Efectivo" else total_a
