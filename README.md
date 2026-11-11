# cli-anything-drawio

Agent-friendly, stateful CLI for **draw.io** diagrams: create, edit and export
`.drawio` files from the terminal (one-shot commands, `--json` output, REPL).
Rendering is done by the real **draw.io Desktop** app.

## Install

```bash
# 1. The real backend (required)
brew install --cask drawio          # macOS  (Linux: snap install drawio, Windows: winget install JGraph.Draw)

# 2. The CLI, straight from GitHub
pip install "git+https://github.com/Marcdaou/cli-anything-drawio.git"
cli-anything-drawio export check
```

## Quick start

```bash
cli-anything-drawio --json project new -o flow.drawio
cli-anything-drawio --json -p flow.drawio shape add -s rounded -l "Start"
cli-anything-drawio -p flow.drawio export render flow.png
```

Run `cli-anything-drawio` with no arguments for the interactive REPL.
Full reference: [`cli_anything/drawio/README.md`](cli_anything/drawio/README.md).
Agent skill: [`skills/cli-anything-drawio/SKILL.md`](skills/cli-anything-drawio/SKILL.md).

Built with the [CLI-Anything](https://github.com/HKUDS/CLI-Anything) methodology. MIT licensed.
