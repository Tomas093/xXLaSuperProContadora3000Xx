import re

# ==========================================
# 1. MOTOR DE LIMPIEZA
# ==========================================
def limpiar_specs(texto):
    """Filtra IDs dinámicos para permitir agrupación."""
    texto = re.sub(r'\s+', ' ', texto).strip()
    # ezdxf ya limpió la basura de AutoCAD, solo nos preocupamos por la lógica de negocio
    if re.fullmatch(r'(ID|Q|KM|F|S|H|X|K)[\s\-:]*[0-9]+[A-Za-z]*', texto, re.IGNORECASE):
        return ""
    return texto


def normalizar_clave(texto):
    """Evita separar grupos por mayúsculas/minúsculas o espacios extra."""
    return re.sub(r'\s+', ' ', texto).strip().casefold()