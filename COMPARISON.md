# RanbooruX vs. Ranbooru — Feature Comparison

This document compares **RanbooruX** (this fork) with the original **Ranbooru** by Inzaniak.

> Scope: based on the shipped UIs (`scripts/ranbooru.py`), READMEs, and installer scripts in the two packages you provided.  
> Generated: 2025-10-01

## TL;DR

- RanbooruX focuses on **stability**, **Forge compatibility**, **img2img + ControlNet reliability**, and **post‑processing with ADetailer**.
- The UI is **expanded and reorganized**: granular tag filters, batch consistency toggles, file‑based inputs, logging, and more.
- Install/updates moved to **`requirements.txt`-based** dependency management; ControlNet helper is **bundled**.
- Credentials UI from the original (API Key/User ID/Status) is removed in favor of a simpler, cookie/anonymous flow.

## Supported boorus

RanbooruX: **aibooru, danbooru, e621, gelbooru, konachan, rule34, safebooru, xbooru, yande.re**  
(Original Ranbooru shipped with a similar set; RanbooruX formalizes the list and normalizes per‑site quirks.)

## Headline differences

- **Architecture**: RanbooruX refactors the monolithic script into clearer components with stronger error handling and logging.
- **Forge-first**: A stable **ControlNet integration** is included (optional drop-in for Forge’s builtin) so img2img → ControlNet is reliable.
- **ADetailer pipeline**: Optional post‑processing pass on each image (off by default).
- **Granular filtering**: Artist/character/series/clothing/furry/headwear/color/subject-count controls split out from “Remove bad tags”.
- **Caching controls**: Separate toggles for **caching API calls** vs **reusing the same fetched posts**.
- **File-driven prompts**: Append a line from *search* files; honor *remove* files; import TXT/CSV; favorites list.
- **Logging**: Optional prompt/source/seeds logging to `user/logs/`.
- **UI polish**: Renamed and clarified options (e.g., “Crop Center” → “Crop image to fit target”).

## One-to-one mapping (renamed/relocated)

| Original Ranbooru | RanbooruX | Notes |
|---|---|---|
| `Fringe Benefits` | `Gelbooru: Fringe Benefits` | renamed for clarity |
| `Use img2img` | `Use Image for Img2Img` | renamed for clarity |
| `Use last image as img2img` | `Use same image for batch` | renamed for clarity |
| `Crop Center` | `Crop image to fit target` | renamed for clarity |
| `Use Deepbooru` | `Use Deepbooru on image` | renamed for clarity |
| `Use tags_search.txt` | `Add line from Search File` | renamed for clarity |
| `Use tags_remove.txt` | `Add tags from Remove File` | renamed for clarity |
| `Use same prompt for all images` | `Use same prompt for batch` | renamed for clarity |
| `Use same seed for all pictures` | `Use same seed for batch` | renamed for clarity |
| `Use cache` | `Cache Booru API requests` | renamed for clarity |
| `Remove bad tags` | `Remove common 'bad' tags` | renamed for clarity |
| `Denoising` | `Img2Img Denoising / CN Weight` | renamed for clarity |
| `Deepbooru Tags Position` | `DB Tags Position` | renamed for clarity |
| `Limit tags` | `Limit tags by %` | renamed for clarity |

## Added in RanbooruX

- `Add favorites`
- `Add line from Search File`
- `Add tags`
- `Add tags from Remove File`
- `Beta: New Tag Filtering`
- `Cache Booru API requests`
- `Crop image to fit target`
- `DB Tags Position`
- `Enable RanbooruX ADetailer support`
- `Favorite Tags`
- `Filter furry/pokémon tags`
- `Filter headwear / halo tags`
- `Gelbooru: Fringe Benefits`
- `Img2Img Denoising / CN Weight`
- `Import CSV/TXT`
- `Keep only subject counts`
- `Limit tags by %`
- `Log image sources/prompts to txt`
- `Mix tags from multiple posts`
- `Posts to mix`
- `Preserve base hair & eye colors`
- `Removal Tags`
- `Remove artist tags`
- `Remove character tags`
- `Remove clothing tags`
- `Remove common 'bad' tags`
- `Remove series / franchise tags`
- `Remove tag/text/commentary metadata`
- `Reuse cached booru posts`
- `Use Deepbooru on image`
- `Use Image for Img2Img`
- `Use same image for batch`
- `Use same prompt for batch`
- `Use same seed for batch`

## Removed/retired from UI

- `API Key`
- `Chaos Mode`
- `Crop Center`
- `Deepbooru Tags Position`
- `Denoising`
- `Fringe Benefits`
- `Limit tags`
- `LoRAs Custom Weights`
- `Max Pages`
- `Max tags`
- `Mix amount`
- `Mix prompts`
- `Negative Mode`
- `Post ID`
- `Remove bad tags`
- `Save credentials`
- `Send to Controlnet`
- `Sorting Order`
- `Status`
- `Use Deepbooru`
- `Use cache`
- `Use img2img`
- `Use last image as img2img`
- `Use same prompt for all images`
- `Use same seed for all pictures`
- `Use tags_remove.txt`
- `Use tags_search.txt`
- `User ID`

> Some retired fields (API Key/User ID/Status/Sorting Order/Max tags) are handled internally or no longer needed in X.
