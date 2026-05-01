# xXLaSuperProContadora3000Xx
La mejor contadora del mercado disponible a tan solo $9999999999999999999999999999999999999

## AI BOM CLI

Run the Claude symbol-counting flow from `proyecto`:

```bash
python3 ai_bom_cli.py --diagram-image test_data/plans/plan1.png
```

By default it reads `.env` from the repository root, so `ANTHROPIC_API_KEY=...` works there too. You can also pass `--api-key`.

The default Claude model is `claude-sonnet-4-6`.

Prompt files live in `proyecto/prompts/bom_symbol_count/`. Use `--prompt-dir` or individual prompt-file flags to test different prompt versions.
