The attached image is the electrical plan.

Generate the BOM by counting symbols in this plan only.

Use:
- the reference table image as the only visual symbol catalog,
- valid_materials JSON as the only allowed list of output material names.

For each counted symbol:
1. Match it visually to one exact symbol in the reference table.
2. Use only the material name associated with that matched reference-table symbol.
3. Confirm that the material name exists exactly in valid_materials.
4. Associate only immediate right-side specification text when present.

Pay special attention to:
- One connected device region can produce at most one BOM symbol.
- Count only complete, standalone, clear visual matches.
- Do not count sub-symbols inside larger symbols.
- Do not count wires, labels, nodes, terminals, annotations, dimensions, or table elements.
- For text-box symbols such as IM, TTAB, or GE, count only if directly connected to a circuit line.
- Same material + same specification must be merged into one BOM row.
- If unsure, put the component-like shape in simbolos_no_identificados.

False positives are unacceptable.
Return only valid JSON.