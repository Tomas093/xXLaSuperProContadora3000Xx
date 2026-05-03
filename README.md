# xXLaSuperProContadora3000Xx
La mejor contadora del mercado disponible a tan solo $9999999999999999999999999999999999999

## AI BOM CLI

Generate BOM JSON/CSV files from electrical plan images using Anthropic, OpenAI, or Gemini.

The examples below assume you are running commands from the repository root:

```bash
python3 proyecto/ai_bom_cli.py ...
```

If your terminal is already inside `proyecto`, remove the `proyecto/` prefix from paths and run:

```bash
python3 ai_bom_cli.py ...
```

### Environment

The CLI only reads API keys from the environment. Provider/model selection is done with CLI flags.

Supported API key names:

- Anthropic/Claude: `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY`
- OpenAI: `OPENAI_API_KEY`
- Gemini: `GEMINI_API_KEY` or `GOOGLE_API_KEY`

If your env file is in `ENV/.env`, pass it explicitly:

```bash
--env-file ENV/.env
```

Or export a key in the current shell:

```bash
export GEMINI_API_KEY="..."
```

### Defaults

- Default provider: `anthropic`
- Default prompt folder: `proyecto/prompts/bom_symbol_count/v4_visual_symbols_only`
- Default symbol folder: `proyecto/test_data/symbols`
- Default catalog: `proyecto/test_data/symbol_catalog.json`

The CLI sends only symbol images listed in `symbol_catalog.json`. It does not send every PNG in `symbols/`.

### Basic Run

```bash
python3 proyecto/ai_bom_cli.py \
  --env-file ENV/.env \
  --diagram-image proyecto/test_data/plans/tscels1.png
```

### Gemini 3 Pro Preview

```bash
python3 proyecto/ai_bom_cli.py \
  --env-file ENV/.env \
  --provider gemini \
  --model gemini-3-pro-preview \
  --diagram-image proyecto/test_data/plans/tstl1n.png \
  --reference-image proyecto/test_data/reference_tables/table1.png \
  --symbols-dir proyecto/test_data/symbols \
  --catalog-json proyecto/test_data/symbol_catalog.json \
  --output-json proyecto/test_data/outputs/gemini/etapa1/tstl1n/tstl1n_gemini3_bom.json \
  --output-csv proyecto/test_data/outputs/gemini/etapa1/tstl1n/tstl1n_gemini3_bom.csv \
  --raw-output proyecto/test_data/outputs/gemini/etapa1/tstl1n/tstl1n_gemini3_raw.txt \
  --usage-output proyecto/test_data/outputs/gemini/etapa1/tstl1n/tstl1n_gemini3_usage.json
```

### Gemini 2.5 Pro

```bash
python3 proyecto/ai_bom_cli.py \
  --env-file ENV/.env \
  --provider gemini \
  --model gemini-2.5-pro \
  --diagram-image proyecto/test_data/plans/tscels1.png \
  --reference-image proyecto/test_data/reference_tables/table1.png \
  --symbols-dir proyecto/test_data/symbols \
  --catalog-json proyecto/test_data/symbol_catalog.json \
  --output-json proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_bom.json \
  --output-csv proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_bom.csv \
  --raw-output proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_raw.txt \
  --usage-output proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_usage.json
```

Use Flash for faster/cheaper tests:

```bash
python3 proyecto/ai_bom_cli.py \
  --env-file ENV/.env \
  --provider gemini \
  --model gemini-2.5-flash \
  --diagram-image proyecto/test_data/plans/tstl1n.png \
  --reference-image proyecto/test_data/reference_tables/table1.png \
  --symbols-dir proyecto/test_data/symbols \
  --catalog-json proyecto/test_data/symbol_catalog.json \
  --output-json proyecto/test_data/outputs/gemini/etapa1/tstl1n/tstl1n_flash_bom.json \
  --output-csv proyecto/test_data/outputs/gemini/etapa1/tstl1n/tstl1n_flash_bom.csv \
  --raw-output proyecto/test_data/outputs/gemini/etapa1/tstl1n/tstl1n_flash_raw.txt \
  --usage-output proyecto/test_data/outputs/gemini/etapa1/tstl1n/tstl1n_flash_usage.json
```

### Save Reference Extraction

Add these flags when you want to save the reference-table JSON and raw model response:

```bash
--reference-output-json proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_reference.json \
--reference-raw-output proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_reference_raw.txt
```

Full example:

```bash
python3 proyecto/ai_bom_cli.py \
  --env-file ENV/.env \
  --provider gemini \
  --model gemini-2.5-pro \
  --diagram-image proyecto/test_data/plans/tscels1.png \
  --reference-image proyecto/test_data/reference_tables/table1.png \
  --symbols-dir proyecto/test_data/symbols \
  --catalog-json proyecto/test_data/symbol_catalog.json \
  --reference-output-json proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_reference.json \
  --reference-raw-output proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_reference_raw.txt \
  --output-json proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_bom.json \
  --output-csv proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_bom.csv \
  --raw-output proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_raw.txt \
  --usage-output proyecto/test_data/outputs/gemini/etapa1/tscels1/tscels1_usage.json
```

### Anthropic/Claude

```bash
python3 proyecto/ai_bom_cli.py \
  --env-file ENV/.env \
  --provider anthropic \
  --model claude-sonnet-4-20250514 \
  --diagram-image proyecto/test_data/plans/tstl1n.png \
  --reference-image proyecto/test_data/reference_tables/table1.png \
  --symbols-dir proyecto/test_data/symbols \
  --catalog-json proyecto/test_data/symbol_catalog.json \
  --output-json proyecto/test_data/outputs/claude/etapa1/tablero-tstl1n/tstl1n_bom.json \
  --output-csv proyecto/test_data/outputs/claude/etapa1/tablero-tstl1n/tstl1n_bom.csv \
  --raw-output proyecto/test_data/outputs/claude/etapa1/tablero-tstl1n/tstl1n_raw.txt \
  --usage-output proyecto/test_data/outputs/claude/etapa1/tablero-tstl1n/tstl1n_usage.json
```

### OpenAI

```bash
python3 proyecto/ai_bom_cli.py \
  --env-file ENV/.env \
  --provider openai \
  --model gpt-5.4-mini \
  --diagram-image proyecto/test_data/plans/tstl1n.png \
  --reference-image proyecto/test_data/reference_tables/table1.png \
  --symbols-dir proyecto/test_data/symbols \
  --catalog-json proyecto/test_data/symbol_catalog.json \
  --output-json proyecto/test_data/outputs/open-ai/etapa1/tstl1n/gpt-5.4-mini/tstl1n_bom.json \
  --output-csv proyecto/test_data/outputs/open-ai/etapa1/tstl1n/gpt-5.4-mini/tstl1n_bom.csv \
  --raw-output proyecto/test_data/outputs/open-ai/etapa1/tstl1n/gpt-5.4-mini/tstl1n_raw.txt \
  --usage-output proyecto/test_data/outputs/open-ai/etapa1/tstl1n/gpt-5.4-mini/tstl1n_usage.json
```

### Prompt Versions

Prompt versions live in `proyecto/prompts/bom_symbol_count/`.

Available folders:

- `v1`
- `v2_no_subsymbols`
- `v3_reference_names_only`
- `v4_visual_symbols_only`

The default is `v4_visual_symbols_only`. To override:

```bash
--prompt-dir proyecto/prompts/bom_symbol_count/v1-gemini-3.1
```

You can also override individual prompt files:

```bash
--plan-system-prompt-file proyecto/prompts/bom_symbol_count/v4_visual_symbols_only/plan_system.md \
--plan-user-prompt-file proyecto/prompts/bom_symbol_count/v4_visual_symbols_only/plan_user.md \
--reference-system-prompt-file proyecto/prompts/bom_symbol_count/v4_visual_symbols_only/reference_system.md \
--reference-user-prompt-file proyecto/prompts/bom_symbol_count/v4_visual_symbols_only/reference_user.md
```

### Output Files

- `--output-json`: normalized BOM JSON
- `--output-csv`: BOM CSV with `material,cantidad`
- `--raw-output`: raw model text for BOM generation
- `--usage-output`: token usage, prompt hashes, timings, and estimated cost
- `--reference-output-json`: optional normalized reference-table JSON
- `--reference-raw-output`: optional raw model text for reference extraction

### Troubleshooting

If you see `No API key was provided`, check the env file path:

```bash
--env-file ENV/.env
```

If you run from inside `proyecto`, use:

```bash
--env-file ../ENV/.env
```

If Gemini returns `503`, the model is temporarily overloaded. Retry later or use `gemini-2.5-flash`.
