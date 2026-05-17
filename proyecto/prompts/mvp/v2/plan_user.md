The image attached is the electrical plan. Generate the BOM by counting symbols in this plan only, using the reference table from the system context as the symbol catalog.
Follow the system rules exactly. Pay special attention to:

Connected device region rule: one connected device region can produce at most one BOM symbol. If a connected region appears to match multiple catalog symbols, count only the largest, most complete, most specific match and reject smaller internal pieces.
Grouping: same material + same specification must produce a single BOM row with a summed quantity. Run a final aggregation pass before returning JSON to eliminate any duplicate (material + specification) rows.
Sub-symbol rule: if a smaller catalog symbol appears as a visual component inside a larger confirmed symbol, count only the larger symbol. Never count both the outer symbol and an internal sub-shape for the same occurrence.
Confidence: only count 100% certain, complete, standalone catalog-symbol matches. If a candidate is probable, partial, similar-looking, or could be a label/callout/terminal/node/line mark, put it in simbolos_no_identificados — do not add it to the BOM. False negatives are better than false positives.
Text-box symbols (IM, TTAB, GE): only count an occurrence when the rectangle is directly connected to a circuit line. Floating boxes or legend/annotation instances are not countable.

Return only valid JSON.
