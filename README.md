# miro-to-obsidian

Migrate a [Miro](https://miro.com) board into [Obsidian](https://obsidian.md) —
either as an **Excalidraw** drawing or an **Obsidian Canvas** file.

The board is read through the Miro REST API and converted shape-by-shape, so the
result preserves positions, colors (incl. fill opacity), borders, fonts, text
alignment, curved connectors with their real attach points, embedded images,
mindmap nodes, and z-ordering.

## Scripts

| Script | Output | Use when |
|---|---|---|
| `miro_to_excalidraw.py` | `.excalidraw` JSON | You use the Obsidian **Excalidraw** plugin |
| `miro_to_canvas.py` | `.canvas` JSON | You prefer native Obsidian **Canvas** |

## Requirements

- Python 3 (standard library only — no dependencies)
- A Miro account with REST API access

## 1. Get a Miro access token

1. Open **miro.com → Profile settings → Your apps** (`https://miro.com/app/settings/user-profile/apps`)
2. **Create new app** → give it a name → Create
3. Under **Permissions**, check **`boards:read`**
4. Click **Install app and get OAuth token** → copy the token

## 2. Get the board ID

From the board URL `https://miro.com/app/board/<BOARD_ID>/`, copy the
`<BOARD_ID>` part (including the trailing `=`).

## 3. Run

```bash
export MIRO_TOKEN="<your-token>"

# Excalidraw
python3 miro_to_excalidraw.py "<BOARD_ID>" "/path/to/board.excalidraw"

# or Obsidian Canvas
python3 miro_to_canvas.py "<BOARD_ID>" "/path/to/board.canvas"
```

Then in Obsidian: `Cmd/Ctrl+P` → **"Excalidraw: Convert .excalidraw files to
Excalidraw drawings"** (Canvas files open directly).

## What gets converted

- **Shapes** → rectangle / ellipse / diamond, with fill color + opacity, border
  color/width/style, and rounded vs sharp corners
- **Text** → real font size, alignment (horizontal + vertical), and font family
  (monospace text stays monospace)
- **Connectors** → arrows attached at Miro's exact attach points; `curved`
  connectors become bowed arcs
- **Images** → embedded into the drawing
- **Mindmap nodes** → text pulled from the experimental mindmap API; filled
  nodes become boxes, unfilled ones stay as plain text
- **Z-order** → larger shapes sent behind smaller ones (Miro's API exposes no
  explicit z-index)

## Limitations

- The Miro API does not expose connector control points, so curved arrows use a
  synthesized bow rather than the exact original curve.
- The Miro API has no z-index field; ordering is inferred from shape area.

## License

MIT

## Fork differences
- Added validation to catch missing or invalid parameters early.
- Ensured the output directory is automatically created if it does not exist or fail if it can not be created.
Before this change, if the output directory did not exist, the script would run for a long time before failing during the output file write.
- Added settings logging and logging during the import process for better visibility.
As it may take quite some time visible progress helps in waiting :)
- Reduced duplicate code around HTTP request execution.
- Added some unit tests.

### Changed success output example
```
Migrate a Miro board into an Excalidraw scene (.excalidraw JSON).

The Obsidian Excalidraw plugin imports .excalidraw files natively (drag into the
vault, or "Convert to Excalidraw drawing"). Miro shapes/sticky-notes/cards/text
become rectangles with bound text; connectors become arrows bound to those
rectangles so they stay attached when you move things around.

Usage:
    export MIRO_TOKEN="<your-access-token>"
    python3 miro_to_excalidraw.py <board_id> <output.excalidraw>

Board id is the part after /board/ in the Miro URL.
Example:
    in url "miro.com/app/board/aaaaaaaaaaa=/" board id is "aaaaaaaaaaa="

Board id: 'aaaaaaaaaaa='
Out path: '/home/user/Documents/Obsidian Vault/MIRO/miro.excalidraw'
Token: 'some token'

Fetching mindmap nodes .
Fetching board items ............................................................................. .................................................................................................................... .............................................................................................................................................................................
Fetching board connectors ...................................................................................................................
Writing imported data -> /home/user/Documents/Obsidian Vault/MIRO/miro.excalidraw...
Wrote 563 shapes, 115 arrows
```

### Errors output example
```
Errors:
<board_id> argument is missing.
<output.excalidraw> argument is missing.
MIRO_TOKEN env var with your Miro access token is missing.

Run command example: python3 miro_to_excalidraw.py "aaaaaaaaaaa=" "/home/user/Documents/Obsidian Vault/MIRO/miro.excalidraw"
```
