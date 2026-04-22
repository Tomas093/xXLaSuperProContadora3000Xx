import pandas as pd
import streamlit as st
import re
import math
import tempfile
import os

# ==========================================
# CATÁLOGO DE BLOQUES
# ==========================================
CATALOGO_BLOQUES = {
    r"Unif-Interruptor-Term|^ITM$": ("Interruptor Termomagnético",   "abajo"),
    r"Unif-Interruptor-Dif|DISYUNTOR": ("Interruptor Diferencial",   "abajo"),
    r"A\$C7AFF483F":                   ("Seccionador Manual",        "arriba"),
    r"^IH$":                           ("Interruptor Horario",       "abajo"),
    r"^AI11$":                         ("Interruptor Automático",    "abajo"),
    r"Int.?Motoriz":                   ("Interruptor Motorizado",    "abajo"),
    r"^I28$":                          ("Interruptor 28",            "abajo"),
    r"Elec.?Medidor":                  ("Medidor",                   "ambos"),
    r"^SBC$":                          ("Seccionador de Barra",      "ambos"),
    r"^ACOM$":                         ("Acometida",                 "ambos"),
    r"Pararrayos":                     ("Pararrayos",                "ambos"),
}

# ==========================================
# PATRONES
# ==========================================
PATRON_AMPERE    = re.compile(r'^\d+[xX×]\d+[aA]$|\d+\s*[aA]$')
PATRON_SENSIB    = re.compile(r'\d+\s*m[aA]', re.IGNORECASE)
PATRON_KA        = re.compile(r'\d+\s*k[aA]', re.IGNORECASE)
PATRON_CIRCUITO  = re.compile(r'^[A-Z]{1,6}-?[A-Z]?\d+$', re.IGNORECASE)
PATRON_CABLE     = re.compile(r'LSOH|NYY|RV|XLP|XLPE|BAND', re.IGNORECASE)
PATRON_NUM_SOLO  = re.compile(r'^\d{1,3}$')
PATRON_LETRA_SLO = re.compile(r'^[RSTPE]$')
PATRON_RST       = re.compile(r'^R-?S-?T$', re.IGNORECASE)

TABLERO_HEADER_RE = re.compile(
    r'^(TABLERO\s+.+|TSET-?\d+|T-?\d+|T\d+)$', re.IGNORECASE
)

# ==========================================
# PARSER DXF
# ==========================================
def parse_dxf_raw(file_path):
    with open(file_path, 'r', encoding='latin-1') as f:
        lines = [l.strip() for l in f.read().split('\n')]

    inserts, texts = [], []
    i = 0
    while i < len(lines):
        if lines[i] == '0' and i + 1 < len(lines):
            etype = lines[i + 1]
            if etype in ('INSERT', 'TEXT', 'MTEXT'):
                entity = {'type': etype}
                i += 2
                while i < len(lines):
                    if lines[i] == '0':
                        break
                    code = lines[i]
                    val  = lines[i + 1] if i + 1 < len(lines) else ''
                    if   code == '2':  entity['name']  = val
                    elif code == '8':  entity['layer'] = val
                    elif code == '10':
                        try: entity['x'] = float(val)
                        except: pass
                    elif code == '20':
                        try: entity['y'] = float(val)
                        except: pass
                    elif code == '1':  entity['text']  = val
                    i += 2
                if etype == 'INSERT':
                    inserts.append(entity)
                else:
                    texts.append(entity)
            else:
                i += 2
        else:
            i += 1

    return inserts, texts

# ==========================================
# RESOLVER BLOQUE
# ==========================================
def resolver_bloque(nombre_raw):
    nombre_corto = nombre_raw.split('$0$')[-1]
    for patron, (nombre_legible, direccion) in CATALOGO_BLOQUES.items():
        if re.search(patron, nombre_corto, re.IGNORECASE):
            return nombre_legible, nombre_corto, direccion
    return nombre_corto, nombre_corto, 'abajo'

# ==========================================
# LIMPIAR TEXTO
# ==========================================
def limpiar_txt(txt):
    txt = re.sub(r'\\[A-Za-z]\d*;', '', txt)
    txt = txt.replace('\\P', ' ')
    return txt.strip()

# ==========================================
# CLASIFICADOR MEJORADO
# ==========================================
def clasificar_spec_texto(txt):
    if not txt or txt == '-':
        return None

    txt = txt.strip()

    if PATRON_LETRA_SLO.match(txt): return None
    if PATRON_NUM_SOLO.match(txt): return None
    if PATRON_CABLE.search(txt): return None

    if re.search(r'\d+\s*[aA].*\d+\s*m[aA]', txt):
        return ('amp_sens', txt)

    if re.search(r'In\s*=\s*\d+\s*[aA]', txt, re.IGNORECASE):
        return ('ampere', txt)

    if re.match(r'^[BCD]\d+$', txt, re.IGNORECASE):
        return ('curva', txt)

    if re.match(r'^\d+[xX×]\d+\s*[aA]', txt):
        return ('ampere', txt)

    if re.search(r'\d+\s*[aA].*curva\s*[A-Z]', txt, re.IGNORECASE):
        return ('amp_curva', txt)

    if PATRON_RST.match(txt): return ('fase', txt)
    if PATRON_SENSIB.search(txt): return ('sensibilidad', txt)
    if PATRON_AMPERE.search(txt): return ('ampere', txt)
    if PATRON_KA.search(txt): return ('poderc', txt)
    if PATRON_CIRCUITO.match(txt): return ('circuito', txt)

    if len(txt) >= 2:
        return ('descripcion', txt)

    return None

# ==========================================
# EXTRAER TABLERO
# ==========================================
def extraer_tablero_de_circuito(txt):
    m = re.match(r'^([A-Z]+-\d[A-Z]?)-', txt, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None

# ==========================================
# MOTOR PRINCIPAL
# ==========================================
def procesar_dxf(uploaded_file, radio_x=2.5, radio_y=3.0):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    inserts_raw, texts_raw = parse_dxf_raw(tmp_path)
    os.unlink(tmp_path)

    # 🔥 capas flexibles
    CAPAS_APARATOS = ['APARATOS', 'EQUIPOS', 'ELEMENTOS', 'BLOQUES']

    aparatos = [
        ins for ins in inserts_raw
        if any(c in ins.get('layer', '').upper() for c in CAPAS_APARATOS)
    ]

    if not aparatos:
        aparatos = inserts_raw

    spec_texts = texts_raw
    all_texts  = texts_raw

    tablero_headers = [
        (t.get('x', 0), t.get('y', 0), t.get('text', '').strip())
        for t in all_texts
        if TABLERO_HEADER_RE.match(t.get('text', '').strip())
    ]

    resultados = []

    for ins in aparatos:
        ix, iy = ins.get('x', 0), ins.get('y', 0)
        nombre_legible, nombre_corto, direccion = resolver_bloque(ins.get('name', ''))

        candidatos = []
        textos_usados = set()

        for t in spec_texts:
            tx, ty = t.get('x', 0), t.get('y', 0)
            dx = tx - ix
            dy = ty - iy

            if abs(dx) > radio_x: continue
            if abs(dy) > radio_y: continue

            txt = limpiar_txt(t.get('text', ''))
            if not txt: continue

            if txt in textos_usados:
                continue
            textos_usados.add(txt)

            candidatos.append((math.sqrt(dx**2 + dy**2), txt))

        candidatos.sort(key=lambda x: x[0])

        roles = {}
        tablero = None

        for _, txt in candidatos:
            rol_data = clasificar_spec_texto(txt)
            if rol_data:
                rol, val = rol_data
                if rol not in roles:
                    roles[rol] = val

                if rol == 'circuito' and not tablero:
                    tablero = extraer_tablero_de_circuito(val)

        if not tablero and tablero_headers:
            tablero = min(tablero_headers,
                          key=lambda h: math.dist((ix, iy), (h[0], h[1])))[2]

        if not tablero:
            tablero = "Sin Tablero"

        orden_roles = [
            'ampere','curva','amp_curva','amp_sens',
            'sensibilidad','poderc','fase','circuito','descripcion'
        ]

        partes = [roles[r] for r in orden_roles if r in roles]
        spec = " | ".join(partes) if partes else "-"

        resultados.append({
            'Tablero': tablero,
            'Componente': nombre_legible,
            'Nombre Bloque': nombre_corto,
            'Especificación': spec,
            'X': round(ix, 2),
            'Y': round(iy, 2),
        })

    df = pd.DataFrame(resultados)

    df_agrupado = (
        df.groupby(['Tablero', 'Componente', 'Especificación', 'Nombre Bloque', 'X', 'Y'])
        .size().reset_index(name='Cantidad')
    )

    resumen_tableros = (
        df_agrupado.groupby('Tablero')['Cantidad']
        .sum().reset_index()
    )

    return df_agrupado, resumen_tableros, ""
def generar_script_zoom_sin_spec(df):
    comandos = []

    comandos.append("ZOOM E")

    for _, row in df.iterrows():
        x = row.get('X')
        y = row.get('Y')

        if x is None or y is None:
            continue

        comandos.append(f"ZOOM C {x},{y} 5")

    return "\n".join(comandos)
# ==========================================
# STREAMLIT
# ==========================================
st.title("La Contadora PRO V6 🔥")

f = st.file_uploader("Subí tu DXF", type=["dxf"])

if f:
    df, resumen, _ = procesar_dxf(f)

    if df.empty:
        st.warning("No se detectó nada")
    else:
        st.success(f"{int(df['Cantidad'].sum())} componentes detectados")

        tableros = ["— Todos —"] + sorted(df['Tablero'].unique())
        sel = st.selectbox("Filtrar por tablero", tableros)

        vista = df if sel == "— Todos —" else df[df['Tablero'] == sel]

        col1, col2 = st.columns([1,3])

        with col1:
            st.dataframe(resumen, use_container_width=True)

        with col2:
            st.dataframe(vista, use_container_width=True)

        sin_spec = vista[vista['Especificación'] == '-']

        if not sin_spec.empty:
            sin_spec = sin_spec.copy()
            script_zoom = generar_script_zoom_sin_spec(sin_spec)

            st.download_button(
                "🔍 Recorrer componentes (zoom x5)",
                script_zoom,
                "zoom_sin_spec.scr",
                "text/plain"
            )

            # 📍 columna lista para copiar
            sin_spec['Coord'] = sin_spec['X'].astype(str) + "," + sin_spec['Y'].astype(str)

            with st.expander("⚠️ Componentes sin especificación"):
                st.dataframe(sin_spec[['Componente', 'Tablero', 'Coord']])
