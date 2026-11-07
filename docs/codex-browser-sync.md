# Codex + existing Chrome sync

This is the preferred personal workflow when the user does not want a separate Holst login or manual file handling.

When the user asks to sync their Greek board:

1. Use the connected, already authenticated Chrome session.
2. Read the board ID and optional display name from the ignored `data/local-board.json`,
   or use the exact board URL supplied by the user. The shared example is
   `examples/local-board.example.json`; it contains no real board identity.
   Open or claim that exact Holst board tab.
3. Click the board export button and select **Download board backup**.
4. Do not read or copy browser cookies, session tokens, or credentials.
5. Wait until Chrome finishes the `.holst` download.
6. Run:

```bash
npm run dev -- import-latest \
  --board-id YOUR_BOARD_ID \
  --name 'Greek lessons' \
  --max-age-minutes 15
```

Replace the placeholders with the local metadata before running the command.
Keep the actual board ID, board name, backups and authentication state under
ignored `data/`; do not add them to shared documentation.

7. Verify `analysis/queue.json` summary counts and inspect failures in `assets/manifest.json`.
   The queue is incremental: only `textItems` and `assetItems` need content review;
   `reusedTextItems` and `reusedAssetItems` must not be reopened.
8. Continue with `docs/codex-analysis-prompt.md`.

This workflow downloads a local backup through the user's authorized UI but requires no manual download, separate login, cookie extraction, or private Holst API credential.
