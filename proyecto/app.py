import pandas as pd
import streamlit as st
from collections import Counter


def contar_simbolos_senior(uploaded_file):
    # Leemos el archivo tolerando cualquier codificación rara
    content = uploaded_file.getvalue().decode('latin-1').splitlines()
    counts = Counter()

    i = 0
    n = len(content)

    while i < n:
        line = content[i].strip()

        # Buscamos la entidad principal (El símbolo insertado en el plano)
        if line == '0' and i + 1 < n and content[i + 1].strip() == 'INSERT':
            nombre_bloque = ""
            atributos = []
            i += 2

            # 1. Buscar el nombre de la instancia (código 2)
            while i < n and content[i].strip() != '0':
                if content[i].strip() == '2':
                    nombre_bloque = content[i + 1].strip()
                i += 2

            # 2. Si la entidad tiene atributos pegados, hacemos drill-down
            while i < n and content[i].strip() == '0':
                tipo_entidad = content[i + 1].strip() if i + 1 < n else ""

                if tipo_entidad == 'ATTRIB':
                    val = ""
                    i += 2
                    # Leemos los datos del atributo hasta la próxima entidad
                    while i < n and content[i].strip() != '0':
                        if content[i].strip() == '1':  # El código 1 almacena el valor del texto
                            val = content[i + 1].strip()
                        i += 2

                    # Filtramos basura típica de plantillas vacías
                    if val and val not in ["?", " ", "X"]:
                        atributos.append(val)

                elif tipo_entidad == 'SEQEND':
                    # Fin de la lista de atributos de este bloque
                    i += 2
                    while i < n and content[i].strip() != '0':
                        i += 2
                    break
                else:
                    # Nos topamos con otra entidad distinta, salimos del bucle
                    break

            # 3. Resolución de identidad para la tabla de cotización
            if nombre_bloque.startswith('*U'):
                if atributos:
                    # Rescatamos el bloque anónimo usando la data técnica que tenía adentro
                    nombre_bloque = f"Componente [*U] -> Info: {' | '.join(atributos)}"
                else:
                    # Si realmente no tiene metadata, lo marcamos para revisión visual
                    nombre_bloque = f"Dinámico sin Atributos ({nombre_bloque})"

            counts[nombre_bloque] += 1
        else:
            i += 1

    return counts


# --- Interfaz Streamlit ---
st.set_page_config(page_title="Cotizador de Materiales", layout="centered")

st.title("⚡ Extractor de Materiales (Deep Scan)")
st.markdown("Sube tu archivo `.dxf` para extraer componentes y revelar metadata de bloques dinámicos.")

file = st.file_uploader("Seleccionar archivo", type=["dxf"])

if file:
    with st.spinner("Parseando árbol de entidades y atributos..."):
        res = contar_simbolos_senior(file)

        if res:
            st.success(f"¡Análisis completo! {sum(res.values())} dispositivos detectados.")

            # Formateo de tabla para fácil lectura
            df = pd.DataFrame(res.items(), columns=['Componente / Especificación', 'Cantidad'])
            df = df.sort_values('Cantidad', ascending=False).reset_index(drop=True)

            st.dataframe(df, use_container_width=True)
        else:
            st.warning("No se detectaron bloques en el archivo.")