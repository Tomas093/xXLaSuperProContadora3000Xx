import pandas as pd
import streamlit as st
import math
import re
from collections import Counter


def limpiar_texto_cad(texto):
    # 1. Quitar basura de formato MTEXT
    t = re.sub(r'\\[A-Za-z0-9~]+[;]', '', texto)
    t = re.sub(r'[{}]', '', t)

    # 2. BORRADO SELECTIVO:
    # Solo borramos si el texto es PURAMENTE un ID (ej: "ID01", "ID-45")
    # Pero si el texto es "Q1" o "KM1", lo DEJAMOS.
    if re.fullmatch(r'ID[\s\-:]*[A-Za-z0-9]+', texto, re.IGNORECASE):
        return ""  # Esto hace que el ID desaparezca de la unión final

    return t.strip()


def agrupar_textos_multiples(uploaded_file):
    try:
        content = uploaded_file.getvalue().decode('latin-1').splitlines()
    except Exception:
        return None

    n = len(content)
    i = 0
    inserts = []
    textos = []

    # 1. ESCANEO DE COORDENADAS
    while i < n:
        line = content[i].strip()

        # Bloques
        if line == '0' and i + 1 < n and content[i + 1].strip() == 'INSERT':
            nombre = ""
            x, y = None, None
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

            if nombre and not nombre.startswith('*U') and x is not None and y is not None:
                inserts.append({'nombre': nombre, 'x': x, 'y': y, 'textos_hijos': []})

        # Textos
        elif line == '0' and i + 1 < n and content[i + 1].strip() in ['TEXT', 'MTEXT']:
            texto = ""
            x, y = None, None
            i += 2
            while i < n and content[i].strip() != '0':
                code = content[i].strip()
                if code == '1':
                    texto = content[i + 1].strip()
                elif code == '10':
                    x = float(content[i + 1].strip())
                elif code == '20':
                    y = float(content[i + 1].strip())
                i += 2

            if texto and x is not None and y is not None:
                txt_limpio = limpiar_texto_cad(texto)

                # Validamos que después de limpiar no haya quedado vacío o sea basura
                if txt_limpio and txt_limpio not in ["?", "X", "ID"]:
                    textos.append({'texto': txt_limpio, 'x': x, 'y': y})
        else:
            i += 1

    # 2. MATCHING INVERSO
    MAX_DISTANCIA = 1.5

    for t in textos:
        bloque_mas_cercano = None
        min_dist = float('inf')

        for idx, ins in enumerate(inserts):
            dx = t['x'] - ins['x']
            dy = t['y'] - ins['y']

            if dx > -20:
                distancia = math.hypot(dx, dy)
                if distancia < min_dist and distancia < MAX_DISTANCIA:
                    min_dist = distancia
                    bloque_mas_cercano = idx

        if bloque_mas_cercano is not None:
            inserts[bloque_mas_cercano]['textos_hijos'].append(t)

    # 3. ORDENAR Y CONCATENAR
    counts = Counter()

    for ins in inserts:
        hijos = ins['textos_hijos']
        if hijos:
            hijos_ordenados = sorted(hijos, key=lambda txt: txt['y'], reverse=True)
            # Unimos los textos, filtrando vacíos (por si el ID era la única palabra y quedó vacío)
            especificacion = " | ".join([txt['texto'] for txt in hijos_ordenados if txt['texto']])
            if not especificacion:  # Si todos los hijos eran IDs que se borraron
                especificacion = "Sin especificación"
        else:
            especificacion = "Sin especificación"

        counts[(ins['nombre'], especificacion)] += 1

    return counts


# --- INTERFAZ DE STREAMLIT ---
st.set_page_config(page_title="Extractor Espacial Múltiple", layout="wide")

st.title("📍 Cómputo por Proximidad (Filtrando IDs Dinámicos)")
st.markdown(
    "Agrupa los componentes, eliminando cualquier etiqueta que empiece con ID (ej. ID02, ID-45) para sumar cantidades correctamente.")

file_dxf = st.file_uploader("Subí tu archivo .dxf", type=["dxf"])

if file_dxf:
    with st.spinner("Procesando y agrupando por especificación..."):
        resultado = agrupar_textos_multiples(file_dxf)

        if resultado:
            st.success(f"¡Listo! {sum(resultado.values())} componentes procesados.")

            filas = []
            for (simbolo, espec), cantidad in resultado.items():
                filas.append({
                    "Componente": simbolo,
                    "Especificación Limpia": espec,
                    "Cantidad": cantidad
                })

            df = pd.DataFrame(filas).sort_values(by=['Componente', 'Cantidad'], ascending=[True, False])
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Descargar CSV Listo para Cotizar", csv, "materiales_agrupados.csv", "text/csv")