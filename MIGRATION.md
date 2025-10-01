# Migrate from Ranbooru → RanbooruX

This guide helps you move existing workflows to RanbooruX without surprises.

## What changed at a glance

- UI was reorganized. Some options were **renamed**, some split into multiple toggles, a few were removed for simplicity.
- Img2Img + ControlNet handoff is **more reliable** on Forge (helper is bundled).
- New **ADetailer** pass can be enabled when needed.
- Caching is **clearer**: API caching vs reusing the same fetched posts.

## Control name changes

| Ranbooru | RanbooruX |
|---|---|
| `Fringe Benefits` | `Gelbooru: Fringe Benefits` |
| `Use img2img` | `Use Image for Img2Img` |
| `Use last image as img2img` | `Use same image for batch` |
| `Crop Center` | `Crop image to fit target` |
| `Use Deepbooru` | `Use Deepbooru on image` |
| `Use tags_search.txt` | `Add line from Search File` |
| `Use tags_remove.txt` | `Add tags from Remove File` |
| `Use same prompt for all images` | `Use same prompt for batch` |
| `Use same seed for all pictures` | `Use same seed for batch` |
| `Use cache` | `Cache Booru API requests` |
| `Remove bad tags` | `Remove common 'bad' tags` |
| `Denoising` | `Img2Img Denoising / CN Weight` |
| `Deepbooru Tags Position` | `DB Tags Position` |
| `Limit tags` | `Limit tags by %` |

## Retired fields

- API Key / User ID / Status — removed from the UI; RanbooruX uses cookie/anonymous access patterns where applicable.
- Sorting Order / Max tags — removed; RanbooruX ships **Limit tags by %** instead.
- Use last image as img2img — use **Use same image for batch**.

## New things to try

- Split removal toggles (artist, character, series, clothing, furry, headwear) for cleaner prompts.
- File‑driven prompts: `Add line from Search File` and `Add tags from Remove File`.
- Optional **ADetailer** for face/object detailing.
- Prompt/source logging to `user/logs/` for reproducibility.
