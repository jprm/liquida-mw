import streamlit as st
import pandas as pd

# Configuración visual
st.set_page_config(page_title="Liquidaciones: Modo Archivos", layout="wide", page_icon="📂")

st.title("📂 Balance de Liquidaciones (Desde Archivos)")
st.markdown("""
**Instrucciones:**
1. Exporta tus tablas (`cortos`, `inscripciones`, `ventas`, `liquidaciones`) como **CSV** desde tu base de datos.
2. Arrástralas a la barra lateral.
3. El sistema cruzará los datos automáticamente.
""")

# ---------------------------------------------------------
# 1. BARRA LATERAL DE CARGA
# ---------------------------------------------------------
st.sidebar.header("1. Sube tus Exportaciones")
st.sidebar.info("Asegúrate de que los CSV incluyan los nombres de columna (header).")

uploaded_cortos = st.sidebar.file_uploader("Tabla: cortos", type=['csv', 'xlsx'])
uploaded_ins = st.sidebar.file_uploader("Tabla: inscripciones", type=['csv', 'xlsx'])
uploaded_ventas = st.sidebar.file_uploader("Tabla: ventas", type=['csv', 'xlsx'])
uploaded_liq = st.sidebar.file_uploader("Tabla: liquidaciones", type=['csv', 'xlsx'])

# Función para leer CSV o Excel indistintamente
def leer_archivo(archivo):
    if archivo is not None:
        try:
            if archivo.name.endswith('.csv'):
                return pd.read_csv(archivo)
            else:
                return pd.read_excel(archivo)
        except Exception as e:
            st.sidebar.error(f"Error leyendo {archivo.name}: {e}")
    return None

# ---------------------------------------------------------
# 2. LÓGICA DE PROCESAMIENTO
# ---------------------------------------------------------

if uploaded_cortos and uploaded_ins and uploaded_ventas and uploaded_liq:
    
    with st.spinner('Procesando datos...'):
        # Cargar DataFrames
        df_cortos = leer_archivo(uploaded_cortos)
        df_ins = leer_archivo(uploaded_ins)
        df_ventas = leer_archivo(uploaded_ventas)
        df_liq = leer_archivo(uploaded_liq)

        # --- A. DEUDAS (INSCRIPCIONES) ---
        # Convertimos columnas a números para evitar errores
        df_ins['fee_cobrado'] = pd.to_numeric(df_ins['fee_cobrado'], errors='coerce').fillna(0)
        df_ins['fee_amount'] = pd.to_numeric(df_ins['fee_amount'], errors='coerce').fillna(0)
        
        # Filtramos: Solo lo NO cobrado (FALSE o 0)
        fees_pendientes = df_ins[df_ins['fee_cobrado'] == 0]
        
        # Agrupamos por corto
        fees_grouped = fees_pendientes.groupby('corto_id')['fee_amount'].sum().reset_index()
        fees_grouped.rename(columns={'fee_amount': 'deuda_fees_cents'}, inplace=True)

        # --- B. LIQUIDACIONES (VENTAS) ---
        # Limpieza de tipos
        df_liq['liquidado'] = pd.to_numeric(df_liq['liquidado'], errors='coerce').fillna(0)
        df_liq['importe_liquidar'] = pd.to_numeric(df_liq['importe_liquidar'], errors='coerce').fillna(0)
        
        # Filtramos: Solo lo NO liquidado
        liq_pendientes = df_liq[df_liq['liquidado'] == 0]
        
        # Unimos con VENTAS para sacar el ID del corto
        # liquidaciones.venta_id <-> ventas.id
        liq_merged = pd.merge(liq_pendientes, df_ventas[['id', 'corto_id']], left_on='venta_id', right_on='id', how='left')
        
        # Agrupamos por corto
        liq_grouped = liq_merged.groupby('corto_id')['importe_liquidar'].sum().reset_index()
        liq_grouped.rename(columns={'importe_liquidar': 'haber_prod_cents'}, inplace=True)

        # --- C. CRUCE FINAL ---
        # Unimos ambas tablas financieras
        df_balance = pd.merge(liq_grouped, fees_grouped, on='corto_id', how='outer').fillna(0)
        
        # Añadimos el Título del corto
        # balance.corto_id <-> cortos.id
        df_balance = pd.merge(df_balance, df_cortos[['id', 'titulo']], left_on='corto_id', right_on='id', how='left')
        df_balance['titulo'] = df_balance['titulo'].fillna('Desconocido / Eliminado')

        # --- D. CÁLCULOS (€) ---
        # Dividimos por 100 porque tus datos vienen en céntimos (30250 -> 302.50)
        df_balance['Haber Productor (€)'] = df_balance['haber_prod_cents'] / 100
        df_balance['Deuda Fees (€)'] = df_balance['deuda_fees_cents'] / 100
        
        # SALDO = (Lo que le tienes que pagar) - (Lo que te debe)
        df_balance['SALDO FINAL'] = df_balance['Haber Productor (€)'] - df_balance['Deuda Fees (€)']

        # ---------------------------------------------------------
        # 3. VISUALIZACIÓN
        # ---------------------------------------------------------

        # Resumen Financiero
        total_pagar = df_balance[df_balance['SALDO FINAL'] > 0]['SALDO FINAL'].sum()
        total_compensado = df_balance[df_balance['SALDO FINAL'] <= 0]['Haber Productor (€)'].sum()
        deuda_viva = df_balance[df_balance['SALDO FINAL'] < 0]['SALDO FINAL'].abs().sum()

        st.subheader("📊 Resumen Global")
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Total a Transferir (Cash Out)", f"{total_pagar:,.2f} €", help="Dinero real que sale de tu banco.")
        col2.metric("🔄 Ventas Compensadas", f"{total_compensado:,.2f} €", help="Dinero de ventas que te quedas para cubrir deudas de fees.")
        col3.metric("📉 Deuda Fees Pendiente", f"{deuda_viva:,.2f} €", delta_color="inverse", help="Dinero que te siguen debiendo tras descontar ventas.")
        
        st.divider()

        # Configuración de Colores y Tabla
        def color_logic(val):
            if val > 0:
                return 'background-color: #d1e7dd; color: #0f5132; font-weight: bold' # Verde
            elif val < 0:
                return 'background-color: #f8d7da; color: #842029; font-weight: bold' # Rojo
            return ''

        # Preparamos DataFrame final para mostrar
        df_show = df_balance[['corto_id', 'titulo', 'Haber Productor (€)', 'Deuda Fees (€)', 'SALDO FINAL']].copy()
        df_show.columns = ['ID', 'Título', 'Ventas Pendientes (+)', 'Deuda Fees (-)', 'A PAGAR / COBRAR']
        df_show = df_show.sort_values('A PAGAR / COBRAR', ascending=False)

        st.write("### 📋 Detalle por Cortometraje")
        st.dataframe(
            df_show.style.format({
                'Ventas Pendientes (+)': '{:.2f} €',
                'Deuda Fees (-)': '{:.2f} €',
                'A PAGAR / COBRAR': '{:.2f} €'
            }).applymap(color_logic, subset=['A PAGAR / COBRAR']),
            use_container_width=True,
            height=800,
            column_config={"ID": st.column_config.NumberColumn(format="%d")}
        )

        # Botón de descarga
        # Preparamos el CSV en formato europeo para que Excel lo abra perfecto
        archivo_csv = df_show.to_csv(
            index=False, 
            sep=';',         # Separador de columnas: punto y coma
            decimal=','      # Separador decimal: coma
        ).encode('utf-8-sig') # 'utf-8-sig' ayuda a Excel a leer acentos y ñ correctamente

        st.download_button(
            label="📥 Descargar Informe Completo (Excel Friendly)",
            data=archivo_csv,
            file_name='balance_liquidaciones_final.csv',
            mime='text/csv'
        )

else:
    # Mensaje de bienvenida cuando no hay archivos
    st.info("👋 Sube los 4 archivos CSV en la barra lateral para ver la magia.")
    
    # Ejemplo visual de ayuda
    with st.expander("¿Qué archivos necesito?"):
        st.write("""
        Exporta las siguientes tablas de tu base de datos:
        1. **cortos**: Para obtener los títulos.
        2. **inscripciones**: Para calcular las deudas de Entry Fees.
        3. **ventas**: Para conectar liquidaciones con cortos.
        4. **liquidaciones**: Para saber qué ventas están pendientes de pago.
        """)