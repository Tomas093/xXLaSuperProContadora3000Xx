# BOM Symbol Count Prompts

Each folder is a prompt version used by the CLI.

Required files per version:

- `plan_system.md`
- `plan_user.md`
- `reference_system.md`
- `reference_user.md`

Default CLI version:

```bash
--prompt-dir prompts/bom_symbol_count/v1-gemini-3.1
```

To test a new prompt version, copy `v1` to a new folder, edit the prompt files, and run:

```bash
python3 ai_bom_cli.py \
  --prompt-dir prompts/bom_symbol_count/v2_no_subsymbols \
  --diagram-image test_data/plans/tscels1.png
```

The usage JSON stores the file path and SHA-256 hash of each prompt file used.
