# RanbooruX

![RanbooruX logo](pics/ranbooru.png)

RanbooruX is a fork of Ranbooru for Stable Diffusion WebUI environments focused on **Forge** and **Forge Neo**.

It fetches booru tags and source images, builds prompts, and supports a two-stage generation flow with optional Img2Img, ControlNet handoff, and ADetailer postprocessing.

## Platform support

- Supported and tested: **Forge**, **Forge Neo**
- Not tested by this project owner: **Automatic1111 (A1111 / A111 WebUI)**

As of **February 13, 2026**, this project owner has only tested RanbooruX on Forge/Forge Neo. If you run A1111, treat support as best-effort and validate manually.

## Why this fork?
- Fix brittle img2img/ControlNet interactions and make them **reliable on Forge and Forge Neo**.
- Split the old “remove bad tags” into **clear, no‑surprise filters**.
- Make installs easy with `requirements.txt` and a bundled ControlNet helper.
- Add **favorites**, **file‑driven prompts**, **logging**, and **sensible caching**.
- ![UI screenshot](pics/image.png)

## What changed since the last published branch

Runtime and workflow changes:

- Hardened Forge/Forge Neo runtime compatibility for Img2Img + ADetailer + ControlNet interactions.
- Added preview guard behavior so intermediate first-pass frames are hidden until final images are ready.
- Kept original prompts in first pass (removed fallback `"abstract shapes, minimal"` replacement).
- Added robust manual ADetailer handling and script-runner guards for extension interoperability.
- Updated `Gelbooru: Fringe Benefits` visibility logic to appear only when `Booru = gelbooru`.
- Redesigned LoRAnado controls with PonyXL-aware scanning, selectable detected LoRAs, and blacklist.
- Added `timm>=0.9.0` to extension requirements for MiDaS depth preprocessor dependency paths.

Filtering and catalog changes:

- Added `Quick Strip` preset in Removal Filters.
- Removed deprecated weapon-tag filtering controls and code remnants.
- Added bundled Danbooru catalog support with import/validation for custom CSV catalogs.
- `Use Danbooru Tag Catalog` is now the default behavior (toggle remains available).

Codebase and maintenance changes:

- Added modular package extraction under `ranboorux/` (`prompting`, `image_ops`, `io_lists`, `catalog`, integrations).
- Added compatibility/integration test suite under `tests/` with Gradio 3/4 coverage.
- Added project tooling and guardrails: `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `pyproject.toml`, and `tools/check_no_gradio_update.py`.
- Removed bundled `scripts/controlnet.py`; runtime integration now resolves external/builtin ControlNet paths.
- Kept `scripts/ranbooru.py` as the WebUI entrypoint while moving reusable logic into modules.

## Installation

1. Copy or clone this repo to your WebUI extensions directory:
   - `extensions/sd-webui-ranbooruX`
2. Start or restart WebUI.
3. `install.py` installs extension dependencies from `requirements.txt`.
4. Open the `RanbooruX` panel.

Optional environment overrides for ControlNet detection:

- `SD_FORGE_CONTROLNET_PATH`
- `RANBOORUX_CN_PATH`

## Quick start

1. Select a booru source.
2. Enter tags and generate.
3. Optional: enable `Use Image for Img2Img`.
4. Optional: enable `Use Image for ControlNet (Unit 0)`.
5. Optional: enable `Enable RanbooruX ADetailer support`.

## Key features

- Booru sources: `aibooru`, `danbooru`, `e621`, `gelbooru`, `gelbooru-compatible`, `konachan`, `rule34`, `safebooru`, `xbooru`, `yande.re`
- Fine-grained removal filters (artist, character, series, clothing, text/commentary, furry, headwear, `*_girl`, subject constraints, and more)
- `Quick Strip` one-click removal preset
- Danbooru tag catalog normalization/filtering (enabled by default, toggleable)
- Img2Img and ControlNet handoff flow
- Optional manual ADetailer pass after Img2Img
- LoRAnado random LoRA injection with PonyXL compatibility controls
- Platform diagnostics panel for runtime visibility
- Caching, file-driven tag sources, favorites, and prompt/source logging

## Removal filters and Quick Strip

`Quick Strip` sets all major removal toggles to ON in one click, including:

- common bad tags
- textual/commentary metadata
- artist/character/series tags
- clothing/furry/headwear tags
- `*_girl` suffix cleanup
- preserve hair/eye colors
- subject-count constraints

This is intended for aggressive prompt cleanup and can be tuned afterward.

## Gelbooru-specific behavior

- `Gelbooru API Key` and `Gelbooru User ID` controls are shown only for Gelbooru.
- `Gelbooru: Fringe Benefits` is shown only when `Booru` is `gelbooru`.
- Credentials can be saved to `user/gelbooru/credentials.json` from UI.

## Danbooru Tag Catalog

RanbooruX includes a bundled catalog used by the redesigned tag-catalog pipeline.

- Bundled file: `data/catalogs/danbooru_tags.csv`
- Catalog mode toggle: `Use Danbooru Tag Catalog` (default ON)
- Source selection: `Bundled` or `Custom file`

With catalog mode enabled (default), the catalog pipeline adds:

- alias normalization
- category-aware filtering
- better hair/eye preservation behavior
- textual/meta tag cleanup backed by catalog categories
- diagnostics panel for kept/dropped/unknown tag insight

Disable the toggle any time to fall back to legacy/non-catalog behavior.

### Custom catalog files

Custom CSV catalogs are supported and imported into `user/catalogs/`.

Accepted formats:

- Header-based CSV (`tag,category,count,alias`)
- Headerless 4-column CSV (`tag,category,count,alias`)

Validation/import controls:

- `Validate CSV`
- `Import Custom Catalog`
- `Reload Catalog`

Implementation details and format notes are documented in:

- `data/catalogs/README.txt`
- `ranboorux/catalog.py`

### Bundled catalog provenance and licensing notes

`data/catalogs/README.txt` includes provenance/licensing context for the bundled `danbooru_tags.csv`, plus references used for the research notes.

## LoRAnado (PonyXL-aware redesign)

LoRAnado now includes detection and control surfaces to reduce incompatible LoRA picks in PonyXL workflows.

Controls:

- `Auto-detect PonyXL-compatible LoRAs`
- `Scan LoRAs`
- `Select All Compatible`
- `Detected LoRAs (toggle enabled)`
- `LoRAnado blacklist`

### PonyXL detection behavior

Detection now prefers strict compatibility signals:

1. Filename token matches (word-boundary aware):
   - `pony`, `pony xl`, `pony-diffusion`, `ponydiffusion`, `pdxl`, `xlp`
2. Metadata matches from relevant base-model/architecture keys only
   - avoids scanning unrelated metadata fields that previously caused false positives

If no compatible LoRAs are detected, RanbooruX falls back to all LoRAs in the selected folder so generation is still usable.

## Two-pass Img2Img + ADetailer notes

For Img2Img workflows, RanbooruX runs an initial pass, then a dedicated Img2Img pass, then optional manual ADetailer processing.

Important behavior:

- first-pass previews are suppressed until final images are ready (preview guard)
- final results are forced back into processed image state for extension/UI consistency
- ADetailer integration uses guarded manual execution to reduce script collisions

## Verification status

The repository includes automated tests for compatibility wrappers, catalog behavior, parsing, and integration boundaries.

Recommended checks:

```bash
PYTHONPATH=/path/to/sd-webui-ranbooruX pytest -q
PYTHONPATH=/path/to/sd-webui-ranbooruX pytest -q --gradio-version=4
python3 -m py_compile scripts/ranbooru.py
```

Additional project-level guidance is in:

- `TESTING.md`
- `PROJECT_STATUS.md`

## Forge/Forge Neo compatibility notes

- Deepbooru support has been removed in RanbooruX.
- The previously bundled `scripts/controlnet.py` has been removed; runtime integration resolves external/builtin ControlNet paths.
- InputAccordion has a fallback for environments where it is unavailable.
- Gradio update calls are routed through compatibility helpers for Gradio 3/4 behavior.

## RanbooruX vs Original Ranbooru

- Project scope: original Ranbooru is mostly a single-script extension; RanbooruX adds a modular package (`ranboorux/`), a full `tests/` suite, CI/pre-commit/tooling config, and contributor/testing docs.
- Core implementation: `scripts/ranbooru.py` is heavily expanded/refactored (about 1.1k lines in original vs about 7.9k lines here) with compatibility wrappers and integration boundaries.
- Feature set: RanbooruX adds Danbooru tag-catalog processing (bundled/custom CSV + validation/import), `Quick Strip`, richer removal filters, and a diagnostics panel.
- Integration flow: RanbooruX hardens Img2Img + ControlNet + ADetailer behavior with safer two-pass processing and guarded/manual ADetailer execution.
- LoRAnado: RanbooruX introduces PonyXL-aware LoRA detection/selection controls and blacklist support.
- Compatibility/dependencies: RanbooruX removes Deepbooru and bundled `scripts/controlnet.py`, and switches installer behavior to `requirements.txt`-driven installs with expanded deps (for example `requests`, `Pillow`, `timm`).

## Credits

- Original Ranbooru by Inzaniak
