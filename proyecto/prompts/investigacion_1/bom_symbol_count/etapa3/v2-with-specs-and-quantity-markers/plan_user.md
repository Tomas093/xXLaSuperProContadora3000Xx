Analyze the provided electrical diagram and symbol catalog.

Reference table JSON:
{reference_table_json}

Task:
- Detect and count symbols in the electrical diagram.
- Each symbol may have a nearby numeric reference ID, such as 1, 2, 3.
- If a numeric reference ID is visible near a symbol, use it to map the symbol to the material description in the reference table JSON.
- If no numeric reference ID is visible, use the provided symbol catalog to identify the material.
- Count repeated branch symbols one by one from left to right.
- Do not estimate repeated quantities.

Specification rule:
- After confirming a symbol, check ONLY for text immediately to the RIGHT of that symbol.
- If such text exists and clearly belongs to that symbol, treat it as the specification.
- If no clear right-side text exists, the specification is null.
- Never use text alone to infer a symbol.

Right-side quantity marker rule:
- If the right-side text is only a standalone marker like "x2", "X2", "x3", or "X3", it is not a specification.
- Count that one visible symbol occurrence as the marker quantity.
- For quantity-marker-only cases, use "especificacion": null.
- Do not confuse specifications like "2x16A" or "4x25A" with quantity markers.
- If a specification and a quantity marker both appear to the right, keep the specification and multiply the quantity by the marker number.

Unidentified device rule:
- If a symbol-like shape or connected component candidate appears in the diagram but is not in the symbol catalog, report it in "simbolos_no_identificados".
- Every visible electrical component candidate must be either counted in "bom" or reported in "simbolos_no_identificados".
- Do not silently ignore component-like shapes only because they are not in the catalog.
- If unsure whether a visible component candidate matches the catalog, report it in "simbolos_no_identificados" instead of forcing a BOM match or omitting it.

Dense-zone counting rule:
- In dense zones, count only complete standalone catalog symbols.
- Do not create extra quantities from nearby line marks, conductor fragments, repeated specification text, or partial symbol strokes.

BOM construction:
- Each component is defined by (material + specification).
- Same material with different specifications must be separate BOM entries.
- Same material with same specification must be grouped.
- Same material with no specification must use "especificacion": null.

Return the BOM as JSON following the required schema.
