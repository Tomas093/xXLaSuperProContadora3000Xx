import pandas as pd
import streamlit as st
from scipy.spatial import cKDTree
import ezdxf
from ezdxf.tools.text import plain_text
import re
import tempfile
import os


# ==========================================
# 1. MOTOR DE LIMPIEZA
# ==========================================
def limpiar_specs(texto):
    """Filtra IDs dinámicos para permitir agrupación."""
    # ezdxf ya limpió la basura de AutoCAD, solo nos preocupamos por la lógica de negocio
    if re.fullmatch(r'(ID|Q|KM|F|S|H|X|K)[\s\-:]*[0-9]+[A-Za-z]*', texto, re.IGNORECASE):
        return ""
    return texto.strip()


# ==========================================
# 2. LECTOR PROFESIONAL (ezdxf)
# ==========================================
def parsear_dxf(file_path):
    """Usa ezdxf para extraer datos puros sin errores de parseo manual."""
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()

    inserts, textos = [], []

    for e in msp:
        if e.dxftype() == 'INSERT':
            nombre = e.dxf.name
            if not nombre.startswith('*U'):  # Seguimos ignorando la basura gráfica
                inserts.append({
                    'nombre': nombre,
                    'x': e.dxf.insert.x,
                    'y': e.dxf.insert.y
                })
        elif e.dxftype() in ('TEXT', 'MTEXT'):
            # ezdxf maneja el formato MTEXT nativamente
            txt = plain_text(e.text) if e.dxftype() == 'MTEXT' else e.dxf.text
            txt = txt.replace('\n', ' ').strip()

            if txt:
                # El punto base de inserción del texto
                pto = e.dxf.insert
                textos.append({'texto': txt, 'x': pto.x, 'y': pto.y})

    return inserts, textos


# ==========================================
# 3. EXTRACCIÓN DE LA TABLA DE REFERENCIAS
# ==========================================
def extraer_tabla_referencias(textos, tol_x, marg_y):
    numeros = [t for t in textos if t['texto'].isdigit()]
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
        num_id = item['texto']
        y_top = item['y'] + (marg_y * 0.5)
        y_bottom = columna_indices[idx + 1]['y'] if idx + 1 < len(columna_indices) else item['y'] - marg_y

        desc_parts = []
        for t in textos:
            dx = t['x'] - item['x']
            if 0.1 < dx < (marg_y * 10) and y_bottom < t['y'] <= y_top:
                if not t['texto'].isdigit():
                    s = limpiar_specs(t['texto'])
                    if s: desc_parts.append(s)

        descripcion = " ".join(desc_parts)
        if descripcion: dict_ref[num_id] = descripcion

    return dict_ref


# ==========================================
# 4. MOTOR ESPACIAL CON SCIPY KD-TREE
# ==========================================
def procesar_con_ml_espacial(uploaded_file, p):
    # ezdxf requiere un archivo físico, usamos tempfile en Windows
    with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    try:
        inserts, textos = parsear_dxf(tmp_path)
    except Exception as e:
        return None, None, None, str(e)
    finally:
        os.unlink(tmp_path)  # Limpiamos la memoria

    # 1. Tabla de referencias
    dict_ref = extraer_tabla_referencias(textos, p['tol_x'], p['marg_y'])

    numeros = [t for t in textos if t['texto'].isdigit()]
    textos_specs = [t for t in textos if not t['texto'].isdigit()]

    # 2. CONSTRUIR KD-TREES (La magia de indexación espacial)
    coords_num = [(n['x'], n['y']) for n in numeros] if numeros else []
    coords_specs = [(t['x'], t['y']) for t in textos_specs] if textos_specs else []

    tree_num = cKDTree(coords_num) if coords_num else None
    tree_specs = cKDTree(coords_specs) if coords_specs else None

    # PASADA 1: Aprender Nombres (Herencia)
    mapa_nombres = {}
    for ins in inserts:
        if tree_num:
            # Busca el número más cercano en microsegundos
            dist, idx = tree_num.query([ins['x'], ins['y']], distance_upper_bound=p['radar_max'])
            if dist != float('inf'):
                num_encontrado = numeros[idx]['texto']
                if num_encontrado in dict_ref:
                    # Guardamos el aprendizaje para este bloque
                    mapa_nombres[ins['nombre']] = dict_ref[num_encontrado]

    # PASADA 2: Agrupación y Confidence Score
    resultados = []

    for ins in inserts:
        nombre_heredado = mapa_nombres.get(ins['nombre'], ins['nombre'])

        # Calcular Confidence Score basado en la distancia del número asociado
        conf_score = 0.0
        if tree_num:
            dist_num, idx_num = tree_num.query([ins['x'], ins['y']], distance_upper_bound=p['radar_max'])
            if dist_num != float('inf'):
                # Fórmula de confianza: 100% si dist=0, decrece hasta 0% en radar_max
                conf_score = round(max(0, 100 * (1 - (dist_num / p['radar_max']))), 1)

        # Buscar especificaciones cercanas con KDTree (query_ball_point busca TODOS los puntos en un radio)
        specs_locales = []
        if tree_specs:
            # Buscamos textos dentro del radio de radar
            indices_cercanos = tree_specs.query_ball_point([ins['x'], ins['y']], r=p['radar_max'])
            for idx in indices_cercanos:
                t = textos_specs[idx]
                dy = t['y'] - ins['y']
                # Filtro fino en Y para no agarrar textos de la fila de arriba/abajo
                if abs(dy) < p['radar_y']:
                    s = limpiar_specs(t['texto'])
                    if s: specs_locales.append(s)

        espec = " | ".join(sorted(specs_locales)) if specs_locales else "-"

        # Agregamos al registro (No usamos Counter directo para poder promediar la confianza)
        resultados.append({
            'Componente': nombre_heredado,
            'Especificación': espec,
            'Confianza': conf_score
        })

    # Agrupar datos con Pandas
    df_crudo = pd.DataFrame(resultados)

    if df_crudo.empty:
        return pd.DataFrame(), dict_ref, mapa_nombres, ""

    # Agrupamos por Componente y Especificación, sumando cantidades y promediando la confianza
    df_agrupado = df_crudo.groupby(['Componente', 'Especificación']).agg(
        Cantidad=('Componente', 'count'),
        Confianza_Promedio=('Confianza', 'mean')
    ).reset_index()

    # Redondeamos la confianza final
    df_agrupado['Confianza_Promedio'] = df_agrupado['Confianza_Promedio'].apply(lambda x: f"{round(x, 1)}%")

    return df_agrupado, dict_ref, mapa_nombres, ""


# ==========================================
# 5. INTERFAZ STREAMLIT
# ==========================================
st.set_page_config(page_title="La Contadora Pro V2 (Industrial)", layout="wide")

st.sidebar.header("⚙️ Parámetros Espaciales (KD-Tree)")
st.sidebar.markdown("Ahora el radar es radial (Euclidiano) gracias a SciPy.")

tx = st.sidebar.number_input("Tolerancia Tabla (X)", value=0.5, step=0.1)
my = st.sidebar.number_input("Banda Tabla (Y)", value=2.0, step=0.1)

st.sidebar.markdown("---")
# En vez de min/max X, KD-Tree usa un radio máximo de búsqueda
r_max = st.sidebar.number_input("Radio de Búsqueda (Max Dist)", value=3.0, step=0.1)
ry = st.sidebar.number_input("Tolerancia Vertical (Y)", value=1.0, step=0.1)

params = {'tol_x': tx, 'marg_y': my, 'radar_max': r_max, 'radar_y': ry}

st.title("xXLaSuperProContadora3000Xx 🏭 (Motor SciPy)")
f = st.file_uploader("Subí tu DWG convertido a DXF", type=["dxf"])

if f:
    with st.spinner("Compilando Árboles KD y matcheando tensores..."):
        df_final, d_ref, mapa, error = procesar_con_ml_espacial(f, params)

        if error:
            st.error(f"Error interno del parser ezdxf: {error}")
        elif not df_final.empty:
            st.success("Cómputo finalizado con indexación espacial.")

            col1, col2 = st.columns(2)
            with col1:
                with st.expander("📖 TABLA DE REFERENCIAS (Auto-detectada)", expanded=False):
                    if d_ref:
                        st.table(pd.DataFrame(list(d_ref.items()), columns=['N°', 'Descripción']))
                    else:
                        st.warning("No se detectó la tabla.")
            with col2:
                with st.expander("🧠 MAPA DE HERENCIA (Símbolo -> Nombre)", expanded=False):
                    st.json(mapa)

            st.markdown("### 📊 Resultado del Cómputo con Nivel de Confianza")

            # Ordenamos por cantidad
            df_final = df_final.sort_values(by=["Cantidad", "Componente"], ascending=[False, True])

            # Usamos st.dataframe que permite ordenar y filtrar en pantalla
            st.dataframe(df_final, use_container_width=True)

            # Botón de descarga
            csv = df_final.to_csv(index=False).encode('utf-8')
            st.download_button("Descargar CSV de Materiales", csv, "computo_scipy.csv", "text/csv")