Analyze the provided electrical diagram image set using the standard symbol catalog JSON and attached symbol images.

Standard symbol catalog mode:
- Use only the provided symbol catalog JSON and attached symbol images to identify materials.
- The catalog "component_name" is the exact material name to use in the BOM.

Task:
- First silently review the full symbol catalog JSON and attached symbol images to bind each actual catalog image to its "component_name".
- Do not write a catalog recognition map, symbol descriptions, or feature lists.
- Then analyze the plan as a staged visual pipeline:
  1. Silent visual catalog binding.
  2. Plan image setup.
  3. Zone setup for each plan image.
  4. Symbol candidate extraction only.
  5. Catalog matching only.
  6. Standalone and sub-symbol validation only.
  7. Local right-side specification extraction only.
  8. Right-side quantity marker interpretation only.
  9. Deduplication only, including cross-image deduplication.
  10. Unknown symbol audit.
  11. BOM grouping only.
  12. Final consistency validation.
- Keep all intermediate phase notes internal and return only the final JSON.
- The input may contain between 1 and 5 plan images.
- If one plan image is provided, return the BOM for that one image.
- If multiple plan images are provided, return ONE complete BOM that sums the confirmed occurrences across all images.
- Treat multiple plan images as evidence for the same final BOM, not as separate output files.
- Detect and count symbols in every provided electrical diagram image.
- Count only complete standalone symbols that visually match the provided symbol catalog.
- Count repeated branch symbols one by one from left to right.
- Do not estimate repeated quantities.
- Do not infer materials from text.
- Do not classify, read specs, apply quantity markers, deduplicate, or group while extracting candidates.
- Enumerate visible candidates first, then classify each candidate against every catalog image.

Specification rule:
- After confirming a standalone catalog symbol, check ONLY for text immediately to the RIGHT of that same symbol.
- If right-side text exists and clearly belongs to that symbol, treat ALL of that text as the specification.
- Do not extract only numbers or amperage values.
- Include curve/type/class text, pole info, KA rating, model text, and any other readable qualifier if it is part of the same right-side specification block.
- If the right-side text is split across multiple lines, combine all lines in reading order into one string.
- Example: right-side text "16A" with "Curva C" below it must be "16A Curva C".
- Example: right-side text "20A" with "Curva C" below it must be "20A Curva C".
- If no clear right-side text exists, the specification is null.
- Never use text alone to infer a symbol.

Right-side quantity marker rule:
- If the right-side text is only a standalone marker like "x2", "X2", "x3", or "X3", it is not a specification.
- Count that one confirmed visible symbol occurrence as the marker quantity.
- For quantity-marker-only cases, use "especificacion": null.
- Do not confuse specifications like "2x16A", "4x25A", "16A Curva C", or "4x25A 10KA" with quantity markers.
- If a specification and a quantity marker both appear to the right, keep the complete specification and multiply the quantity by the marker number.
- A quantity marker can only multiply an already confirmed visible standalone symbol.

Unidentified device rule:
- If a symbol-like shape or connected component candidate appears in the diagram but is not in the symbol catalog, report it in "simbolos_no_identificados".
- Every visible symbol-like electrical component candidate, excluding obvious wires, text, tables, borders, dimensions, and purely graphical connection marks, must be either counted in "bom" or reported in "simbolos_no_identificados".
- Do not silently ignore component-like shapes only because they are not in the catalog.
- If unsure whether a visible component candidate matches the catalog, report it in "simbolos_no_identificados" instead of forcing a BOM match or omitting it.

Dense-zone counting rule:
- In dense zones, count only complete standalone catalog symbols.
- Do not create extra quantities from nearby line marks, conductor fragments, repeated specification text, or partial symbol strokes.
- Do not count sub-symbols or internal fragments of a larger confirmed symbol.

BOM construction:
- Each component is defined by (material + specification).
- Same material with different specifications must be separate BOM entries.
- Same material with same specification must be grouped.
- Same material with no specification must use "especificacion": null.
- Group only after every confirmed occurrence has been enumerated and deduplicated.
- The final quantity is the sum of confirmed occurrences across all provided plan images.

Return the BOM as JSON following the required schema.
