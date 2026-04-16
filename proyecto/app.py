import pandas as pd
import streamlit as st
import math
import re
from collections import Counter


# ==========================================
# 1. MOTOR DE LIMPIEZA
# ==========================================
def limpiar_specs(texto):
    """Limpia formato y vuela IDs de instancia (Q1, ID02) para poder agrupar."""
    t = re.sub(r'\\[A-Za-z0-9~]+[;]', '', texto)
    t = re.sub(r'[{}]', '', t)
    # Filtro para ignorar Tags (Q1, KM1, ID20) que rompen el conteo de iguales
    if re.fullmatch(r'(ID|Q|KM|F|S|H|X|K)[\s\-:]*[0-9]+[A-Za-z]*', t, re.IGNORECASE):
        return ""
    return t.strip()


# ==========================================
# 2. LECTOR DE TABLA DE REFERENCIAS (FASE 0)
# ==========================================
def extraer_tabla_referencias(content, tol_x, marg_y):
    n = len(content)
    i = 0
    textos_crudos = []

    while i < n:
        line = content[i].strip()
        if line == '0' and i + 1 < n and content[i + 1].strip() in ['TEXT', 'MTEXT']:
            texto, x, y = "", None, None
            i += 2
            while i < n and content[i].strip() != '0':
                code = content[i].strip()
                if code in ['1', '3']:
                    texto += content[i + 1].strip()
                elif code == '10':
                    x = float(content[i + 1].strip())
                elif code == '20':
                    y = float(content[i + 1].strip())
                i += 2
            if texto and x is not None and y is not None:
                textos_crudos.append({'texto': texto, 'x': x, 'y': y})
        else:
            i += 1

    numeros = [t for t in textos_crudos if t['texto'].strip().isdigit()]
    if not numeros: return {}

    grupos_x = {}
    for num in numeros:
        x_aprox = round(num['x'] / tol_x) * tol_x
        if x_aprox not in grupos_x: grupos_x[x_aprox] = []
        grupos_x[x_aprox].append(num)

    columna_indices = max(grupos_x.values(), key=len)
    columna_indices = sorted(columna_indices, key=lambda t: t['y'], reverse=True)

    dict_ref = {}
    for idx, item in enumerate(columna_indices):
        num_id = item['texto'].strip()
        y_top = item['y'] + (marg_y * 0.5)
        y_bottom = columna_indices[idx + 1]['y'] if idx + 1 < len(columna_indices) else item['y'] - marg_y

        desc_parts = []
        for t in textos_crudos:
            dx = t['x'] - item['x']
            if 0.1 < dx < (marg_y * 10) and y_bottom < t['y'] <= y_top:
                if not t['texto'].strip().isdigit():
                    s = limpiar_specs(t['texto'])
                    if s: desc_parts.append(s)

        descripcion = " ".join(desc_parts)
        if descripcion: dict_ref[num_id] = descripcion

    return dict_ref


# ==========================================
# 3. PROCESO DE DOBLE PASADA (HERENCIA)
# ==========================================
def procesar_con_herencia(uploaded_file, p):
    try:
        content = uploaded_file.getvalue().decode('latin-1').splitlines()
    except:
        return None, None, None

    # 1. Extraer Referencias
    dict_ref = extraer_tabla_referencias(content, p['tol_x'], p['marg_y'])

    n, i = len(content), 0
    inserts, textos = [], []

    # Recolección (Filtrando *U de entrada)
    while i < n:
        line = content[i].strip()
        if line == '0' and i + 1 < n and content[i + 1].strip() == 'INSERT':
            nombre, x, y = "", None, None
            i += 2
            while i < n and content[i].strip() != '0':
                code = content[i].strip()
                if code == '2':
                    nombre = content[i + 1].strip()
                elif code == '10':
                    x = float(content[i + 1].strip())
                elif code == '20':
                    y = float(content[i + 1].strip())
                i += 2
            if nombre and not nombre.startswith('*U'):
                inserts.append({'nombre': nombre, 'x': x, 'y': y})
        elif line == '0' and i + 1 < n and content[i + 1].strip() in ['TEXT', 'MTEXT']:
            txt, x, y = "", None, None
            i += 2
            while i < n and content[i].strip() != '0':
                code = content[i].strip()
                if code == '1':
                    txt = content[i + 1].strip()
                elif code == '10':
                    x = float(content[i + 1].strip())
                elif code == '20':
                    y = float(content[i + 1].strip())
                i += 2
            if txt: textos.append({'texto': txt, 'x': x, 'y': y})
        else:
            i += 1

    # PASADA 1: Aprender nombres de los símbolos
    mapa_nombres = {}
    for ins in inserts:
        for t in textos:
            dx, dy = t['x'] - ins['x'], t['y'] - ins['y']
            if (p['radar_x_min'] < dx < p['radar_x_max']) and (abs(dy) < p['radar_y']):
                raw = t['texto'].strip()
                if raw.isdigit() and raw in dict_ref:
                    mapa_nombres[ins['nombre']] = dict_ref[raw]

    # PASADA 2: Agrupar por nombre heredado + especificación local
    counts = Counter()
    for ins in inserts:
        nombre_heredado = mapa_nombres.get(ins['nombre'], ins['nombre'])

        specs_locales = []
        for t in textos:
            dx, dy = t['x'] - ins['x'], t['y'] - ins['y']
            if (p['radar_x_min'] < dx < p['radar_x_max']) and (abs(dy) < p['radar_y']):
                raw = t['texto'].strip()
                if not raw.isdigit():
                    s = limpiar_specs(raw)
                    if s: specs_locales.append(s)

        espec = " | ".join(sorted(specs_locales)) if specs_locales else "-"
        counts[(nombre_heredado, espec)] += 1

    return counts, dict_ref, mapa_nombres


# ==========================================
# 4. INTERFAZ
# ==========================================
st.set_page_config(page_title="La Contadora Pro", layout="wide")

st.sidebar.header("⚙️ Parámetros Decimales")
tx = st.sidebar.number_input("Tolerancia Tabla (X)", value=0.5, step=0.1)
my = st.sidebar.number_input("Banda Tabla (Y)", value=2.0, step=0.1)
rx_min = st.sidebar.number_input("Radar X Min", value=-1.0, step=0.1)
rx_max = st.sidebar.number_input("Radar X Max", value=3.0, step=0.1)
ry = st.sidebar.number_input("Radar Y Lim", value=1.0, step=0.1)

params = {'tol_x': tx, 'marg_y': my, 'radar_x_min': rx_min, 'radar_x_max': rx_max, 'radar_y': ry}

st.title("xXLaSuperProContadora3000Xx ⚡")
f = st.file_uploader("Subí tu DXF", type=["dxf"])

if f:
    res, d_ref, mapa = procesar_con_herencia(f, params)
    if res:
        st.success("Cómputo finalizado.")

        # EL DESPLEGABLE QUE PEDISTE
        with st.expander("📖 TABLA DE REFERENCIAS DETECTADA"):
            if d_ref:
                st.table(pd.DataFrame(list(d_ref.items()), columns=['N°', 'Descripción']))
            else:
                st.warning("No se detectó la tabla. Ajustá 'Tolerancia Tabla' o 'Banda Tabla'.")

        with st.expander("🧠 MAPA DE HERENCIA (Símbolo -> Nombre)"):
            st.json(mapa)

        st.markdown("### 📊 Resultado del Cómputo")
        data = [{"Componente": c, "Especificación": e, "Cantidad": v} for (c, e), v in res.items()]
        df = pd.DataFrame(data).sort_values(["Componente", "Cantidad"], ascending=[True, False])
        st.dataframe(df, use_container_width=True)

        st.download_button("Bajar CSV", df.to_csv(index=False).encode('utf-8'), "computo.csv")