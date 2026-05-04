Analyze the provided electrical diagram and symbol catalog.

Reference table JSON:
{reference_table_json}

Task:
- Detect and count symbols in the electrical diagram.
- Each symbol may have a nearby numeric reference ID, such as 1, 2, 3.
- If a numeric reference ID is visible near a symbol, use it to map the symbol to the material description in the reference table JSON.
- If no numeric reference ID is visible, use the provided symbol catalog to identify the material.

Specification rule:
- After confirming a symbol, check ONLY for text immediately to the RIGHT of that symbol.
- If such text exists and clearly belongs to that symbol, treat it as the specification.
- If no clear right-side text exists, the specification is null.
- Never use text alone to infer a symbol.

BOM construction:
- Each component is defined by (material + specification).
- Same material with different specifications must be separate BOM entries.
- Same material with same specification must be grouped.
- Same material with no specification must use "especificacion": null.

Return the BOM as JSON following the required schema.