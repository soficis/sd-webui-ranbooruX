<div align="center">

# RanbooruX

![RanbooruX logo](pics/ranbooru.png)

RanbooruX is a fork of Ranbooru built **exclusively for Forge Neo**, featuring native support for **ADetailer Neo**.

</div>

It fetches booru tags and source images, builds prompts, and supports a two-stage generation flow with Img2Img, ControlNet handoff, and ADetailer / ADetailer Neo postprocessing.

## Features & Exclusive Fork Capabilities

RanbooruX delivers massive architectural and feature upgrades over original Ranbooru:

- **Forge Neo & ADetailer Neo Native Support**: Built exclusively for Forge Neo, with full support for ADetailer Neo and standard ADetailer in two-pass Img2Img workflows.
- **Anima (2B DiT) Support**: Native auto-detection of Anima models with automatic flow-matching scheduler tuning, prompt quality prefixes, and working basic Img2Img support.
- **Danbooru Tag Catalog System**: Bundled tag catalog (`data/catalogs/danbooru_tags.csv`) providing alias normalization, category-aware filtering, custom CSV import, and hair/eye color preservation.
- **Safer Two-Pass Img2Img & Guarded Postprocessing**: Preview guard suppresses initial-pass flashes until final img2img outputs are rendered; guarded script runner prevents script collisions.
- **Rich Booru & Tag Removal Filters**: Multi-booru search (`aibooru`, `danbooru`, `e621`, `gelbooru`, `konachan`, `rule34`, `safebooru`, `xbooru`, `yande.re`) with fine-grained removal toggles (artist, character, series, clothing, commentary, furry, headwear, `*_girl` suffix cleanup).
- **LoRAnado Random LoRA Injection**: Automatic detection and control surfaces for PonyXL & Anima-compatible LoRAs with blacklist support.
- **Modular Codebase & Quality Tooling**: Refactored from a monolithic script into a clean `ranboorux/` module with unit tests (`pytest`), strict type checking (`mypy`), linting (`ruff`), and formatting (`black`).
- **User Conveniences**: Favorites management, file-driven tag sources, prompt/source logging, and sensible caching.

![UI screenshot](pics/image.png)

## Installation

### Method 1: Install from URL in Forge Neo (Recommended)

1. Open **Forge Neo**.
2. Navigate to the **Extensions** tab -> **Install from URL** sub-tab.
3. Paste the URL of this repository into **URL for extension's git repository**:
   `https://github.com/soficis/sd-webui-ranbooruX`
4. Click **Install**.
5. Restart **Forge Neo** or click **Apply and restart UI**.

### Method 2: Manual Installation

1. Copy or clone this repository to your WebUI extensions directory:
   - `extensions/sd-webui-ranbooruX`
2. Start or restart WebUI.
3. `install.py` installs extension dependencies from `requirements.txt`.
4. Open the **RanbooruX** panel.

### Environment Configuration Overrides

RanbooruX supports optional environment variables to override ControlNet detection paths:

- `SD_FORGE_CONTROLNET_PATH`: Custom path to the Forge ControlNet extension or module directory.
- `RANBOORUX_CN_PATH`: Custom path to ControlNet model or script assets monitored by RanbooruX.

## Quick start

1. Select a booru source.
2. Enter tags and generate.
3. Optional: enable `Use Image for Img2Img`.
4. Optional: enable `Use Image for ControlNet (Unit 0)`.
5. Optional: enable `Enable RanbooruX ADetailer support` (supports both ADetailer and ADetailer Neo).

## Danbooru Tag Catalog

RanbooruX includes a bundled catalog used by the tag-catalog pipeline.

- Bundled file: `data/catalogs/danbooru_tags.csv`
- Catalog mode toggle: `Use Danbooru Tag Catalog` (default ON)
- Source selection: `Bundled` or `Custom file`

With catalog mode enabled (default), the catalog pipeline adds:

- alias normalization
- category-aware filtering
- better hair/eye preservation behavior
- textual/meta tag cleanup backed by catalog categories

### Custom catalog files

Custom CSV catalogs are supported and imported into `user/catalogs/`.

Accepted formats:
- Header-based CSV (`tag,category,count,alias`)
- Headerless 4-column CSV (`tag,category,count,alias`)

Validation and import controls (`Validate CSV`, `Import Custom Catalog`, `Reload Catalog`) are available in the UI.

## Two-Pass Img2Img + ADetailer / ADetailer Neo Pipeline

For Img2Img workflows, RanbooruX executes an initial pass, followed by an Img2Img pass, and an optional manual ADetailer / ADetailer Neo postprocessing pass.

- First-pass previews are suppressed until final images are ready (preview guard).
- Final results are forced back into processed image state for extension and UI consistency.
- Native script discovery automatically detects both standard ADetailer and ADetailer Neo at gather and removal stages.

## Anima Model Support

RanbooruX natively supports **Anima** (a 2B parameter DiT model by CircleStone Labs + Comfy Org built on NVIDIA Cosmos-Predict2) in Forge Neo with basic Img2Img support fully working.

### Anima ControlNet Support

RanbooruX supports **basic ControlNet Img2Img & conditioning handoff** for Anima models.

Anima uses a 2B Diffusion Transformer (DiT) architecture, which requires specialized **ControlNet-LLLite** models rather than standard SD/SDXL ControlNets:

- **Available LLLite Models**: `anima-lllite-lineart-1` (line art / pose guidance), `anima-lllite-depth-1` (depth estimation guidance), `anima-lllite-inpainting-v2` (targeted inpainting).
- **How to Use**:
  1. Open Forge Neo's **ControlNet** panel (Unit 0 tab).
  2. Select an Anima LLLite model (`anima-lllite-lineart-1` or `anima-lllite-depth-1`) and matching preprocessor (`anime_lineart` or `depth`).
  3. In RanbooruX, check **`Use Image for ControlNet (Unit 0)`**.
  4. Click **Generate** — RanbooruX automatically passes the fetched booru image to Unit 0.
- **Scope & Limitations**: RanbooruX handles standard ControlNet LLLite image handoff into Unit 0. Anima Edit (Cosmos-Reference) is not supported.

### How "ControlNet Unit 0" Works in Forge Neo

In Forge Neo, ControlNet units are 0-indexed under the hood:
- **Unit 0** corresponds to the **1st ControlNet tab/accordion slot** in Forge Neo's ControlNet interface.
- When **`Use Image for ControlNet (Unit 0)`** is enabled, RanbooruX automatically fetches the target booru image and populates Unit 0's control image slot before triggering generation.

### Understanding & Customizing Anima Settings

When an Anima model is loaded and **`Auto-detect Anima model`** is enabled:
- **Tag Formatting**: Automatically converts underscores (`_`) to spaces (e.g. `blue_hair` → `blue hair`) for Anima's Qwen3 text encoder.
- **Default Quality Prefix**: Auto-prepends `masterpiece, best quality, score_7, safe, ` if no quality tags are present.
- **Default Negative Prompt**: Auto-fills default negative prompt (`worst quality, low quality, score_1, score_2...`) if negative prompt is empty.
- **Customization**: Uncheck **`Auto-detect Anima model`** to bypass default quality prefixes and negative prompts for 100% custom prompt construction.

### How to Control Anima Sampler Tuning

RanbooruX includes dedicated UI controls for Anima sampler and step optimization:

- **`Auto-tune Img2Img parameters for Anima`** (`anima_tune_img2img`, default ON):
  - **When Enabled**: Automatically optimizes step counts, CFG scale (3.0–6.0), and denoising strength (capped at 0.5) tuned for Anima's flow-matching scheduler during Img2Img passes.
  - **When Disabled**: RanbooruX preserves your manual step count, CFG scale, and denoising strength set in Forge Neo, giving full manual control to users who prefer custom sampler settings.

### Recommended Settings
- CFG: 4–5
- Steps: 30–50
- Sampler: Euler a or er_sde
- Resolution: 512²–1536²
- Clip Skip: 1

## RanbooruX vs Original Ranbooru

Original Ranbooru was a monolithic single-script extension (~1.1k lines). RanbooruX is a complete overhaul built specifically for Forge Neo:

| Aspect | Original Ranbooru | RanbooruX |
| --- | --- | --- |
| **Target Platform** | Legacy SD WebUI / A1111 | Exclusively **Forge Neo** & **ADetailer Neo** |
| **Architecture** | Single file (`scripts/ranbooru.py`) | Modular package (`ranboorux/`) + script wrappers |
| **Anima Model Support** | None | Full auto-detection, quality defaults, working Img2Img & ControlNet (LLLite) |
| **ADetailer Integration** | None / basic script calling | Guarded two-pass runner supporting ADetailer & ADetailer Neo |
| **Tag Processing** | Ad-hoc string replacements | Bundled Danbooru Tag Catalog (`data/catalogs/danbooru_tags.csv`) |
| **Testing & Quality** | No tests | Complete `pytest` test suite, `mypy`, `ruff`, `black` & CI |
| **Dependency Management** | Implicit / unmanaged | Automated via `requirements.txt` & `install.py` |

## Forge Neo Technical Notes

- Target Platform: Developed and tested **strictly for Forge Neo only**. Other WebUI distributions are not supported or tested.
- ControlNet integration is designed for Forge Neo and tested only in that environment.
- Deepbooru support has been removed in RanbooruX.
- The previously bundled `scripts/controlnet.py` has been removed; runtime integration dynamically resolves external/builtin ControlNet paths.
- InputAccordion includes compatibility fallbacks for environments where it is unavailable.
- Gradio update calls are routed through compatibility helpers for Gradio 3/4 behavior.

## Verification Status

RanbooruX includes automated test coverage for wrappers, catalog behavior, parsing, and integration boundaries.

Run checks locally:

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. pytest -q --gradio-version=4
python3 -m ruff check scripts/ranbooru.py ranboorux tests tools install.py
python3 -m black --check scripts/ranbooru.py ranboorux tests tools install.py
python3 -m mypy ranboorux --warn-return-any --warn-unused-ignores
```

## LoRAnado (PonyXL & Anima detection)

> [!NOTE]
> LoRAnado is a legacy feature inherited from original Ranbooru.

LoRAnado includes detection and control surfaces to reduce incompatible LoRA picks in PonyXL and Anima workflows.

Controls:
- `Auto-detect PonyXL/Anima-compatible LoRAs`
- `Scan LoRAs`
- `Select All Compatible`
- `Detected LoRAs (toggle enabled)`
- `LoRAnado blacklist`

Detection matches PonyXL and Anima model signatures based on filename tokens and model metadata keys. If no compatible LoRAs are detected, RanbooruX falls back to all LoRAs in the target directory.

## Credits

- Original Ranbooru by Inzaniak
