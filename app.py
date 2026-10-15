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
    session_init.add(Repuesto(codigo="EM-205", descripcion="Kit Distribución Completo Ka 1.5", marca="
