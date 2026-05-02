# xXLaSuperProContadora3000Xx
La mejor contadora del mercado disponible a tan solo $9999999999999999999999999999999999999

## AI BOM CLI

Run the AI symbol-counting flow from `proyecto`:

```bash
python3 ai_bom_cli.py --diagram-image test_data/plans/plan1.png
```

By default it reads `.env` from the repository root. Claude/Anthropic remains the default provider, so the current setup keeps working:

```bash
ANTHROPIC_API_KEY=...
```

You can switch provider and model from the CLI:

```bash
python3 ai_bom_cli.py --provider anthropic --model claude-sonnet-4-6 --diagram-image test_data/plans/plan1.png
python3 ai_bom_cli.py --provider openai --model gpt-4o --diagram-image test_data/plans/plan1.png
python3 ai_bom_cli.py --provider gemini --model gemini-1.5-pro --diagram-image test_data/plans/plan1.png
```

Supported env vars are only for API keys:

- Claude/Anthropic: `ANTHROPIC_API_KEY`
- OpenAI: `OPENAI_API_KEY`
- Gemini: `GEMINI_API_KEY` or `GOOGLE_API_KEY`

Models are selected with `--model` or the provider default. API URLs are provider defaults.

Prompt files live in `proyecto/prompts/bom_symbol_count/`. Use `--prompt-dir` or individual prompt-file flags to test different prompt versions.
