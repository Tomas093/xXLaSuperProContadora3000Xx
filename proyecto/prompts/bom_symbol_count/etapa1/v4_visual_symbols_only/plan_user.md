Analyze the provided electrical diagram and symbol catalog.

Reference table JSON:
{reference_table_json}

Task:
- Detect and count symbols in the electrical diagram.
- Each symbol may have a nearby numeric reference ID, such as 1, 2, 3.
- If a numeric reference ID is visible near a symbol, use it to map the symbol to the material description in the reference table JSON.
- If no numeric reference ID is visible, use the provided symbol catalog to identify the material.

Return the BOM as JSON following the required schema.
