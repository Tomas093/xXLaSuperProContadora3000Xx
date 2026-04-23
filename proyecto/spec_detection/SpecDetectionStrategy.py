from abc import ABC, abstractmethod
from typing import TypedDict

from .utils import limpiar_specs
from typing import TypedDict

class SpecDetectionStrategy(ABC):
    key = ""
    label = ""

    @abstractmethod
    def find_spec(self, ins, textos_specs, tree_specs, params) -> DetectedSpec | None:
        raise NotImplementedError

class DetectedSpec(TypedDict):
    texto: str
    x: float
    y: float

class RightSideAutoStrategy(SpecDetectionStrategy):
    key = "right_auto"
    label = "A la derecha (auto)"

    def find_spec(self, ins, textos_specs, tree_specs, params)-> DetectedSpec | None:
        if tree_specs is None:
            return None

        candidatos = []
        indices_cercanos = tree_specs.query_ball_point([ins['x'], ins['y']], r=params['radio_auto'])

        for idx in indices_cercanos:
            t = textos_specs[idx]
            dx = t['x'] - ins['x']
            dy = t['y'] - ins['y']
            texto_limpio = limpiar_specs(t['texto'])

            if dx <= 0 or not texto_limpio:
                continue

            distancia = (dx ** 2 + dy ** 2) ** 0.5
            score = distancia + abs(dy) * 2
            candidatos.append((score, distancia, abs(dy), dx, t))

        if not candidatos:
            return None

        candidatos.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        return candidatos[0][4]
