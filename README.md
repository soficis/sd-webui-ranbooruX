# RanbooruX

![Alt text](pics/ranbooru.png)

RanbooruX is an extension for the [automatic111 Stable Diffusion UI](https://github.com/AUTOMATIC1111/stable-diffusion-webui) and Forge. It adds a panel that fetches tags (and optionally source images) from multiple boorus to quickly generate varied prompts and test models.

## About This Fork
The primary purpose of this fork is to resolve core **img2img** and **ControlNet** integration issues present in the original Ranbooru repository. **RanbooruX** enables their seamless combination while incorporating extensive refactoring and custom Forge UI scripts to supplant the original ones, addressing critical bugs and performance errors.

### Technical Enhancements
RanbooruX is not just a bugfix; it's a complete architectural overhaul designed for stability, maintainability, and modern development practices.

#### 1. Core Script Refactoring
The original procedural `ranbooru.py` script was fully refactored into an Object-Oriented architecture.
-   **API Abstraction**: A base `Booru` class now manages common API request logic, error handling, and caching. Each specific booru (e.g., `Gelbooru`, `Danbooru`) inherits from this class, drastically reducing code duplication and making it easier to add new boorus.
-   **Robust Error Handling**: Network timeouts, HTTP errors, and invalid API responses are now gracefully handled with `try...except` blocks and a custom `BooruError` exception, preventing silent failures.
-   **Improved Readability**: The code is organized into smaller, single-responsibility functions with consistent logging (`[R] ...`) for easier debugging.

*   **Robust Data Fetching in RanbooruX:**
    ```python
    class Booru():
        # ...
        def _fetch_data(self, query_url):
            print(f"[R] Querying {self.booru_name}: {query_url}")
            try:
                res = requests.get(query_url, headers=self.headers, timeout=30)
                res.raise_for_status()
                # ...
            except requests.exceptions.RequestException as e:
                print(f"[R] Error fetching data from {self.booru_name}: {e}")
                raise BooruError(f"HTTP Error fetching from {self.booru_name}: {e}") from e
    ```

#### 2. Stable ControlNet Integration for SD Forge
RanbooruX features a stable, built-in integration with ControlNet that isolates it from breaking changes in the main ControlNet extension.
-   **Bundled ControlNet Module**: A self-contained copy of the necessary ControlNet API files is included in the `sd_forge_controlnet` directory. This ensures that RanbooruX's core functionality remains stable even if the user's main ControlNet extension is updated or changed.
-   **Structured API Interaction**: The integration uses a `ControlNetUnit` data class (`lib_controlnet/external_code.py`) as a structured payload to reliably send the fetched image and settings to a ControlNet unit.

#### 3. Modernized Installation and Dependency Management
The installation process was updated to follow modern Python best practices.
-   **From Hardcoded to `requirements.txt`**: The original `install.py` performed a single, hardcoded dependency check. The new version reads dependencies from `requirements.txt`, allowing for version pinning and easier management of multiple packages for both the main extension and the bundled ControlNet module.

*   **Modernized `install.py` in RanbooruX:**
    ```python
    import os
    import launch
    # ...
    def _install_req(path, desc):
        if os.path.exists(path):
            try:
                launch.run_pip(f"install -r \"{path}\"", desc)
            # ...
    _install_req(os.path.join(ext_root, "requirements.txt"), "RanbooruX requirements")
    _install_req(os.path.join(ext_root, "sd_forge_controlnet", "requirements.txt"), "...")
    ```

For a full list of user-facing changes, see the [CHANGELOG.md](CHANGELOG.md).
## Installation
- Clone or copy this repo into your Stable Diffusion WebUI extensions directory (Forge or A1111 compatible).
- Dependencies are installed automatically by `install.py` (or run `pip install -r requirements.txt`).
- Restart the WebUI and look for the "RanbooruX" panel.

## Features
The extension is now divided into two main functionalities that can be used together or separately:
### RanbooruX
This is the main part of the extension. It gets a random set of tags from boorus pictures.  
Here's an explanation of all the parameters:
- **Booru**: The booru to get the tags from. Right now Gelbooru, Rule34, Safebooru, yande.re, konachan, aibooru, danbooru and xbooru are implemented. You can easily add more creating a class for the booru and adding it to the booru list in the script.

### Supported Boorus and API Details
`gelbooru`, `danbooru`, `xbooru`, `rule34`, `safebooru`, `konachan`, `yande.re`, `aibooru`, `e621`.

#### API Compatibility Matrix

| Booru | Multi-Tag Search | Post ID Support | Rating System | Tag Categorization | Special Features |
|-------|------------------|-----------------|---------------|-------------------|------------------|
| **Danbooru** | ❌ Single tag only | ✅ Full | 4-tier custom | ✅ Structured | High-quality art |
| **Gelbooru** | ✅ Complex queries | ✅ Full | 3-tier standard | Manual parsing | Fringe Benefits option |
| **Safebooru** | ✅ Multi-tag | ✅ Full | None (SFW only) | Directory-based | SFW content focus |
| **Rule34.xxx** | ✅ Multi-tag | ✅ Full | 3-tier standard | Flat strings | Adult content |
| **Konachan** | ✅ Multi-tag | ❌ Not supported | 3-tier standard | ✅ Structured | High-quality curated |
| **Yande.re** | ✅ Multi-tag | ❌ Not supported | 3-tier standard | ✅ Structured | High-quality curated |
| **e621** | ✅ Complex queries | ❌ Not supported | Custom | ✅ Highly structured | Furry/anthro focus |
| **AIBooru** | ✅ Multi-tag | ❌ Not supported | 3-tier standard | Flat strings | AI-generated focus |
| **XBooru** | ✅ Multi-tag | ✅ Full | 3-tier standard | Directory-based | Alternative to Gelbooru |

#### Important API Limitations
- **Post ID Restrictions**: `konachan`, `yande.re`, and `e621` APIs don't support direct post ID lookups
- **Danbooru Tag Limit**: Only single tags supported (e.g., "1girl" works, "1girl solo" fails)
- **Rate Limiting**: All boorus implement rate limiting; RanbooruX uses intelligent caching to minimize API calls
- **Authentication**: All endpoints are public; no authentication required but some may have stricter limits

- **Max Pages**: Maximum pages considered when selecting random posts.
- **Post ID**: Here you can specify the ID of the post to get the tags from. If you leave it blank, the extension will get a random post (or more than one) from the random page.
- **Tags to Search (Pre)**: This add the tags you define (this should be separated by commas e.g: 1girl,solo,short_hair) to the search query. This is useful if you want to get tags from a specific category, like "1girl" or "solo". Add `!refresh` to force fetch new images instead of reusing cached ones (e.g., `1girl,solo,short_hair,!refresh`).
- **Tags to Remove (Post)**: This remove the tags you define (this should be separated by commas e.g: 1girl,solo,short_hair) from the result query. This is useful if you want to remove tags that are too generic, like "1girl" or "solo". You can also use * with any tag to remove every tags which contains the related word. e.g: *hair will remove every tag that contains the word "hair".
- **Mature Rating**: This sets the mature rating of the booru. This is useful if you want to get only SFW or NSFW tags. It only works on supported boorus (right now it has been tested only on Gelbooru).
- **Remove Bad Tags**: This remove tags that you usually don't need (watermarks,text,censor)
- **Remove Artist tags from prompt**: Automatically removes artist tags (like artist names) from the generated prompt
- **Remove Character tags from prompt**: Automatically removes character tags (like character names from series) from the generated prompt
- **Shuffle Tags**: This shuffle the tags before adding them to the text.
- **Convert** "_" to Spaces": This convert _ to spaces in the tags.
- **Use the same prompt for all images**: This use the same prompt for all the generated images in the same batch. If not selected, each image will have a different prompt.
- **Limit Tags**: Limit number of tags by percent or absolute maximum.
- **Max Tags**: Cap the number of tags used.
- **Change Background**: "Add Detail", "Force Simple", "Force Transparent/White".
- **Change Color**: "Force Color", "Force Monochrome".
- **Sorting Order**: "Random", "Score Descending", "Score Ascending" (post-fetch ordering).
- **Use img2img**: Use the source image with a separate Img2Img pass.
- **Send to ControlNet**: Sends image to ControlNet Unit 0 (uses ControlNet external API with automatic p.script_args fallback).
- **Denoising Strength**: Strength for Img2Img / ControlNet weight.
- **Use last image as img2img**: Reuse same source image across the batch.
- **Crop Center**: Center crop before Img2Img.
- **Use Deepbooru**: Tag fetched images with Deepbooru, with merge mode (Add Before/After/Replace).
- **Use tags_search.txt** / **Use tags_remove.txt**: Read additional tags from `extensions/<this>/user/search` and `user/remove`.
- **Mix Prompts** and **Mix Amount**: Mix tags from multiple posts.
- **Chaos Mode** and **Chaos Amount**: Shuffle tags toward negative (Shuffle All / Shuffle Negative).
- **Use Same Seed**: Repeat seed across batch.
- **Use Cache**: Cache API responses with `requests-cache`.

### LoRAnado
Pick random LoRAs from a folder and add them to the prompt:
- **Lock Previous LoRAs**: Uses the same LoRAs of the previous generation. This is useful if you've found an interesting combination and you want to test it with different tags.
- **LoRAs Subfolder**: The subfolder of the LoRAs folder to use. This is required.
- **LoRAs Amount**: The amount of LoRAs to use.
- **Min LoRAs Weight**: The minimum weight of the LoRAs to use in the prompt.
- **Max LoRAs Weight**: The maximum weight of the LoRAs to use in the prompt.
- **LoRAs Custom Weights**: Here you can specify the weight to use with the random LoRAs (separated by commas). If you leave it blank, the extension will use the min and max weights. Example: if you have 3 LoRAs you can write: 0.2,0.3,0.5.

### Advanced Features
RanbooruX includes several advanced features for more granular control over prompt generation and batch processing.

-   **Advanced Prompt Manipulation**: Fine-tune prompts with features like mixing tags from multiple posts, introducing controlled chaos by shuffling tags between positive and negative prompts, and using file-based tag collections for easy reuse.
-   **LoRAnado**: Automatically select and apply LoRAs from a specified subfolder with customizable weights, making it easy to experiment with different model combinations.
-   **Enhanced Batch Processing**: Ensure consistency across batches with options to use the same prompt, source image, and seed for all generated images.
-   **Image Caching and Refresh**: RanbooruX automatically caches fetched images and posts to improve performance. Add `!refresh` to your search tags to force fetch new images instead of reusing cached ones. The cache is automatically invalidated when search parameters change.
-   **Photopea Integration**: The bundled ControlNet module includes a direct integration with Photopea, allowing for in-browser editing of ControlNet input images without leaving the Stable Diffusion UI.

For more details on these features, see the [usage.md](usage.md) file.
## How to Use
For step-by-step examples and detailed guides, please refer to [usage.md](usage.md).
### Bundled processing scripts
- `Comments` (now bundled): removes `#`, `//`, and `/* */` comments from prompts and negative prompts before other scripts run. It is shipped inside this extension (`scripts/comments.py`) so Forge/A1111 will load it automatically with RanbooruX enabled. Note: While bundled with RanbooruX, this script may not be necessary for all users depending on their workflow and other extensions.

### Bundled ControlNet and paths
- `sd_forge_controlnet/` is bundled for compatibility. RanbooruX will try to use Forge’s built‑in ControlNet first, then this bundled copy if needed. During install, its requirements are auto‑installed.
- You can explicitly point to a ControlNet install by setting one of these env vars before launch:
  - `SD_FORGE_CONTROLNET_PATH` or `RANBOORUX_CN_PATH` → folder containing `lib_controlnet/external_code.py` (for example your Forge built‑in `extensions-builtin/sd_forge_controlnet`).

#### Optional: enable full Img2Img + ControlNet on Forge
If your Forge build does not pass the Img2Img source image to ControlNet Unit 0 by default, you can use the modified ControlNet script bundled with RanbooruX:

1. Make a backup of your original file:
   - `webui\extensions-builtin\sd_forge_controlnet\scripts\controlnet.py`
2. Copy the bundled file over it:
   - From `extensions\sd-webui-ranbooruX\sd_forge_controlnet\scripts\controlnet.py`
   - To `webui\extensions-builtin\sd_forge_controlnet\scripts\controlnet.py`
3. Restart the WebUI.

Note: Overwriting is optional and only needed if your current Forge ControlNet does not pick up Img2Img inputs properly with RanbooruX. Keep your backup so you can restore the original at any time.

### ControlNet behavior on Forge
- Forge’s ControlNet does not expose the A1111 helper functions RanbooruX would use to update units programmatically.
- As a result, RanbooruX uses the reliable fallback (p.script_args) to pass the image and weight to Unit 0 when you enable “Use Image for ControlNet”. This is expected and working.
- You’ll see a concise log indicating which path was taken:
  - External API path: `[R Before] ControlNet configured via external_code.`
  - Fallback path: `[R Before] ControlNet using fallback p.script_args hack.`

## Known Issues
- The chaos mode and negative mode can return an error when using a batch size greater than 1 combined with a batch count greater than 1. Rerunning the batch usually fixes the issue.
- "sd-dynamic-prompts" creates problems with the multiple prompts option. Disabling the extension is the only solution for now.
- Right now to run the img2img the extension creates an img with 1 step before creating the actual image. I don't know how to fix this, if someone want to help me with this I'd be grateful.
- Send to controlnet needs an dummy image to work.
---
## Original Repo by Inzaniak
