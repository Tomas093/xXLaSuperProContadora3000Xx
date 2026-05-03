# AI BOM CLI Data

Optional local sample files for the AI symbol-counting BOM flow.

Recommended structure:

- `reference_tables/`
  - Image of the references table extracted from the drawing.
- `plans/`
  - Plan or electrical panel images to analyze.
- `symbols/`
  - One image per material.
- `outputs/`
  - Generated JSON, raw text, and CSV files from CLI runs.

Example:

- `reference_tables/panel_a_refs.png`
- `plans/panel_a_plan.png`
- `symbols/contactor_3p.png`
- `symbols/contactor_4p.png`
- `symbols/relay_24v.png`

Edit `symbol_catalog.json` so each `filename` matches the real file inside `symbols/`.

Suggested workflow:

1. Put your shared files in:
   - `reference_tables/` for the reference table image
   - `symbols/` for the symbol PNGs
   - `symbol_catalog.json` for symbol metadata
2. Make sure `symbol_catalog.json` has exactly one entry per material:
   - `filename`: image file inside `symbols/`
   - `component_name`: exact Spanish material name to use in the BOM
3. Run the CLI from the `proyecto` folder:
   - `python3 ai_bom_cli.py --diagram-image test_data/plans/plan1.png`

Notes:

- By default the CLI reads `.env` from the repository root. Claude/Anthropic remains the default provider, so `ANTHROPIC_API_KEY` still works.
- Use `--provider`, `--model`, and `--api-key` to test other providers rapidly.
- Supported providers: `anthropic`, `openai`, and `gemini`.
- Prompt versions live in `../prompts/bom_symbol_count/` and can be selected with `--prompt-dir`.
- The JSON output has `bom` and `simbolos_no_identificados`.
- The CSV output is generated from `bom` with columns `material,cantidad`.
