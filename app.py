import streamlit as st
import pandas as pd

# Configuración de la página
st.set_page_config(page_title="Gestor Real de Liquidaciones", layout="wide", page_icon="🎬")

st.title("🎬 Balance Real: Liquidaciones vs. Entry Fees")
st.markdown("""
Sube tus archivos **CSV** exportados de la base de datos para cruzar automáticamente:
1. Lo que debes a los productores (Liquidaciones pendientes).
2. Lo que los productores te deben a ti (Entry Fees no pagados).
""")

# ---------------------------------------------------------
# 1. ZONA DE CARGA DE ARCHIVOS (SIDEBAR)
# ---------------------------------------------------------
st.sidebar.header("📂 Sube tus tablas aquí")

file_cortos = st.sidebar.file_uploader("Tabla: cortos", type=["csv"])
file_inscripciones = st.sidebar.file_uploader("Tabla: inscripciones", type=["csv"])
file_ventas = st.sidebar.file_uploader("Tabla: ventas", type=["csv"])
file_liquidaciones = st.sidebar.file_uploader("Tabla: liquidaciones", type=["csv"])

def load_csv(file):
    if file is not None:
        return pd.read_csv(file)
    return None

# ---------------------------------------------------------
# 2. PROCESAMIENTO DE DATOS
# ---------------------------------------------------------

if file_cortos and file_inscripciones and file_ventas and file_liquidaciones:
    
    # Cargar DataFrames
    try:
        df_cortos = load_csv(file_cortos)
        df_ins = load_csv(file_inscripciones)
        df_ventas = load_csv(file_ventas)
        df_liq = load_csv(file_liquidaciones)

        # --- A. PREPARACIÓN DE DEUDAS (ENTRY FEES) ---
        # Filtramos donde fee_cobrado es Falso (0)
        # Aseguramos que fee_cobrado sea numérico para filtrar bien
        df_ins['fee_cobrado'] = pd.to_numeric(df_ins['fee_cobrado'], errors='coerce').fillna(0)
        df_ins['fee_amount'] = pd.to_numeric(df_ins['fee_amount'], errors='coerce').fillna(0)
        
        fees_pendientes = df_ins[df_ins['fee_cobrado'] == 0].copy()
        
        # Agrupamos por corto_id
        fees_grouped = fees_pendientes.groupby('corto_id')['fee_amount'].sum().reset_index()
        fees_grouped.rename(columns={'fee_amount': 'deuda_fees_raw'}, inplace=True)

        # --- B. PREPARACIÓN DE LIQUIDACIONES (VENTAS) ---
        # 1. Filtramos liquidaciones pendientes (liquidado = 0)
        df_liq['liquidado'] = pd.to_numeric(df_liq['liquidado'], errors='coerce').fillna(0)
        df_liq['importe_liquidar'] = pd.to_numeric(df_liq['importe_liquidar'], errors='coerce').fillna(0)
        
        liq_pendientes = df_liq[df_liq['liquidado'] == 0].copy()
        
        # 2. Unimos con VENTAS para obtener el corto_id
        # Liquidaciones (venta_id) -> Ventas (id) ... Ventas (corto_id)
        liq_merged = pd.merge(liq_pendientes, df_ventas[['id', 'corto_id']], left_on='venta_id', right_on='id', how='left')
        
        # 3. Agrupamos por corto_id
        liq_grouped = liq_merged.groupby('corto_id')['importe_liquidar'].sum().reset_index()
        liq_grouped.rename(columns={'importe_liquidar': 'haber_prod_raw'}, inplace=True)

        # --- C. CRUCE FINAL (MASTER MERGE) ---
        
        # Unimos las dos tablas financieras (Outer join para no perder nada)
        df_balance = pd.merge(liq_grouped, fees_grouped, on='corto_id', how='outer')
        
        # Rellenamos NaNs con 0 (importante para las restas)
        df_balance = df_balance.fillna(0)
        
        # Añadimos el TÍTULO del corto
        df_balance = pd.merge(df_balance, df_cortos[['id', 'titulo']], left_on='corto_id', right_on='id', how='left')
        
        # Limpieza final de título
        df_balance['titulo'] = df_balance['titulo'].fillna('Corto Desconocido / Eliminado')

        # --- D. CÁLCULOS MONETARIOS (Céntimos a Euros) ---
        # Según tus datos: 30250 = 302.50€ (dividir entre 100)
        
        df_balance['A Favor Productor (€)'] = df_balance['haber_prod_raw'] / 100
        df_balance['Deuda Entry Fees (€)'] = df_balance['deuda_fees_raw'] / 100
        
        # BALANCE: (Lo que le debes) - (Lo que te debe)
        df_balance['SALDO FINAL'] = df_balance['A Favor Productor (€)'] - df_balance['Deuda Entry Fees (€)']

        # ---------------------------------------------------------
        # 3. VISUALIZACIÓN
        # ---------------------------------------------------------
        
        # KPIs Superiores
        total_pagar_real = df_balance[df_balance['SALDO FINAL'] > 0]['SALDO FINAL'].sum()
        total_recuperado = df_balance[df_balance['SALDO FINAL'] <= 0]['A Favor Productor (€)'].sum() 
        # Nota: total_recuperado es dinero que NO sale de tu caja porque se compensó con deuda
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total a Transferir (Cash Out)", f"{total_pagar_real:,.2f} €")
        col2.metric("Deuda Recuperada (Compensada)", f"{total_recuperado:,.2f} €", help="Dinero de ventas que te quedas para cubrir deudas de fees")
        col3.metric("Deuda Fees Restante", f"{df_balance[df_balance['SALDO FINAL'] < 0]['SALDO FINAL'].abs().sum():,.2f} €", delta_color="inverse", help="Dinero que los productores aun te deben tras descontar ventas")

        st.divider()

        # Estilos para la tabla
        def highlight_rows(val):
            if val > 0:
                # Verde: Hay que pagar
                return 'background-color: #d4edda; color: #155724; font-weight: bold'
            elif val < 0:
                # Rojo: Sigue debiendo dinero
                return 'background-color: #f8d7da; color: #721c24; font-weight: bold'
            else:
                return ''

        # Preparar tabla para mostrar
        display_cols = ['corto_id', 'titulo', 'A Favor Productor (€)', 'Deuda Entry Fees (€)', 'SALDO FINAL']
        df_display = df_balance[display_cols].sort_values('SALDO FINAL', ascending=False)
        
        # Renombrar para vista
        df_display.columns = ['ID', 'Título', 'Liquidación (70%)', 'Deuda Fees', 'A PAGAR / COBRAR']

        st.write("### 📋 Detalle por Cortometraje")
        st.dataframe(
            df_display.style.format({
                'Liquidación (70%)': '{:.2f} €',
                'Deuda Fees': '{:.2f} €',
                'A PAGAR / COBRAR': '{:.2f} €'
            }).applymap(highlight_rows, subset=['A PAGAR / COBRAR']),
            use_container_width=True,
            height=600,
            column_config={"ID": st.column_config.NumberColumn(format="%d")}
        )
        
        # Botón descarga
        csv = df_display.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Descargar Informe CSV",
            data=csv,
            file_name="balance_liquidaciones_real.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"Error al procesar los archivos: {e}")
        st.warning("Por favor revisa que los archivos CSV tengan las columnas correctas (corto_id, fee_amount, venta_id, importe_liquidar, etc).")

else:
    st.info("👈 Por favor, sube los 4 archivos CSV en el menú de la izquierda para comenzar.")
    st.image("https://cdn-icons-png.flaticon.com/512/4205/4205906.png", width=100) # Icono CSV decorativo