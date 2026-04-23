import pandas as pd
import streamlit as st
from scipy.spatial import cKDTree
import ezdxf
from ezdxf.tools.text import plain_text
import tempfile
import os
import shutil
from spec_detection.utils import limpiar_specs, normalizar_clave
from spec_detection.registry import SPEC_STRATEGIES
from dwg_converter.dwg_converter import CadConversionService


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

def preparar_archivo_cad(uploaded_file):
    temp_dir = tempfile.mkdtemp(prefix="contadora_cad_")
    nombre = uploaded_file.name.lower()
    extension = ".dwg" if nombre.endswith(".dwg") else ".dxf"

    input_path = os.path.join(temp_dir, "input" + extension)
    dxf_path = os.path.join(temp_dir, "input.dxf")

    with open(input_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    if extension == ".dwg":
        converter = CadConversionService()
        converter.convert(input_path, dxf_path)
    else:
        dxf_path = input_path

    return dxf_path, temp_dir

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
def procesar_con_ml_espacial(uploaded_file, p, spec_strategy):
    temp_dir = None
    try:
        tmp_path, temp_dir = preparar_archivo_cad(uploaded_file)
        inserts, textos = parsear_dxf(tmp_path)
    except Exception as e:
        return None, None, None, str(e)
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # 1. Tabla de referencias
    dict_ref = extraer_tabla_referencias(textos, p['tol_x'], p['marg_y'])

    numeros = [t for t in textos if t['texto'].isdigit()]
    textos_specs = [t for t in textos if not t['texto'].isdigit()]

    # 2. CONSTRUIR KD-TREES (La magia de indexación espacial)
    coords_num = [(n['x'], n['y']) for n in numeros] if numeros else []
    coords_specs = [(t['x'], t['y']) for t in textos_specs] if textos_specs else []

    tree_num = cKDTree(coords_num) if coords_num else None
    tree_specs = cKDTree(coords_specs) if coords_specs else None

    # Mapa informativo. La agrupación real se hace por cada instancia, no por bloque global.
    mapa_nombres = {}

    # PASADA 2: Agrupación
    resultados = []

    for ins in inserts:
        nombre_final = ins['nombre']
        if nombre_final == ins['nombre'] and ins['nombre'].startswith('*'):
            continue

        # La asociación de nombre final se resolverá en otra refactorización.

        # La detección de especificación sí depende de la estrategia activa.
        specs_por_clave = {}
        mejor_spec = spec_strategy.find_spec(ins, textos_specs, tree_specs, p)
        if mejor_spec:
            t = mejor_spec
            s = limpiar_specs(t['texto'])
            if s:
                specs_por_clave.setdefault(normalizar_clave(s), s)

        specs_ordenadas = [
            specs_por_clave[clave]
            for clave in sorted(specs_por_clave)
        ]
        espec = " | ".join(specs_ordenadas) if specs_ordenadas else "-"

        # Agregamos al registro (No usamos Counter directo para poder promediar la confianza)
        resultados.append({
            'Componente': nombre_final,
            'Especificación': espec,
            'Componente_Key': normalizar_clave(nombre_final),
            'Especificación_Key': normalizar_clave(espec),
        })

    # Agrupar datos con Pandas
    df_crudo = pd.DataFrame(resultados)

    if df_crudo.empty:
        return pd.DataFrame(), dict_ref, mapa_nombres, ""

    # Agrupamos por claves normalizadas para que la misma especificación cuente junta.
    df_agrupado = df_crudo.groupby(['Componente_Key', 'Especificación_Key']).agg(
        Componente=('Componente', 'first'),
        Especificación=('Especificación', 'first'),
        Cantidad=('Componente', 'count'),
    ).reset_index()

    df_agrupado = df_agrupado.drop(columns=['Componente_Key', 'Especificación_Key'])

    # Redondeamos la confianza final

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
estrategia_key = st.sidebar.selectbox(
    "Estrategia para detectar especificación",
    options=list(SPEC_STRATEGIES.keys()),
    format_func=lambda key: SPEC_STRATEGIES[key].label,
)
radio_auto = st.sidebar.number_input("Radio automático de búsqueda", value=20.0, step=1.0)

params = {'tol_x': tx, 'marg_y': my, 'radio_auto': radio_auto}
spec_strategy = SPEC_STRATEGIES[estrategia_key]

st.title("xXLaSuperProContadora3000Xx 🏭 (Motor SciPy)")
f = st.file_uploader("Subí tu DWG convertido a DXF", type=["dxf"])

if f:
    with st.spinner("Compilando Árboles KD y matcheando tensores..."):
        df_final, d_ref, mapa, error = procesar_con_ml_espacial(f, params, spec_strategy)

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
