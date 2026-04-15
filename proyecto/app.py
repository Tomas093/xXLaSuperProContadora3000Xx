import pandas as pd
import streamlit as st
from collections import Counter


def contar_simbolos_bruto(uploaded_file):
    # Leemos el archivo como texto usando 'latin-1'
    # para que no explote con los acentos de AutoCAD
    content = uploaded_file.getvalue().decode('latin-1').splitlines()

    counts = Counter()
    i = 0
    n = len(content)

    while i < n:
        line = content[i].strip()

        # En el estándar DXF, '0' seguido de 'INSERT' indica un bloque (símbolo)
        if line == '0' and i + 1 < n and content[i + 1].strip() == 'INSERT':
            i += 2
            # Buscamos la etiqueta '2', que es el nombre del bloque
            while i < n and content[i].strip() != '0':
                if content[i].strip() == '2' and i + 1 < n:
                    nombre_bloque = content[i + 1].strip()
                    counts[nombre_bloque] += 1
                    break
                i += 2
        else:
            i += 1

    return counts


# --- Interfaz Streamlit ---
st.title("📊 Contador de Símbolos (Brute Force Mode)")

file = st.file_uploader("Subí el archivo bueno.dxf", type=["dxf"])

if file:
    res = contar_simbolos_bruto(file)

    if res:
        st.success(f"¡Analizado con éxito! Se encontraron {sum(res.values())} elementos.")
        df = pd.DataFrame(res.items(), columns=['Símbolo', 'Cantidad']).sort_values('Cantidad', ascending=False)
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("No se encontraron bloques 'INSERT'. ¿Seguro que los símbolos no están explotados?")