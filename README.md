# RanbooruX
![Alt text](pics/ranbooru.png)
RanbooruX is an extension for the [automatic111 Stable Diffusion UI](https://github.com/AUTOMATIC1111/stable-diffusion-webui) and Forge. It adds a panel that fetches tags (and optionally source images) from multiple boorus to quickly generate varied prompts and test models.
![Alt text](pics/image.png)

## About this fork — short summary

RanbooruX is an actively maintained, extensively refactored fork of the original Ranbooru with a focus on reliability and Forge/A1111 compatibility. Concise highlights:

- Refactor & reorganization for maintainability and clearer code structure.
- Img2Img pipeline fixes so source images are used reliably in img2img passes.
- Robust ControlNet integration with an external-API path and a p.script_args fallback for Forge builds.
- UI cleanup and improved prompt/control options.
- Bundled helper scripts (e.g., `Comments`) and request caching via `requests-cache`.

See `CHANGELOG.md` for the full, detailed list of changes and migration notes.

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

### Supported boorus
`gelbooru`, `danbooru`, `xbooru`, `rule34`, `safebooru`, `konachan`, `yande.re`, `aibooru`, `e621`.

Notes:
- Some APIs restrict post ID lookups: `konachan`, `yande.re`, and `e621` don’t support `Post ID` in this extension.
- `danbooru` only supports a single tag in API search queries.
- Some sites may require credentials or rate-limit unauthenticated requests. RanbooruX uses public endpoints; if access is restricted by the site, consider using alternative boorus.

- **Max Pages**: Maximum pages considered when selecting random posts.
- **Post ID**: Here you can specify the ID of the post to get the tags from. If you leave it blank, the extension will get a random post (or more than one) from the random page.
- **Tags to Search (Pre)**: This add the tags you define (this should be separated by commas e.g: 1girl,solo,short_hair) to the search query. This is useful if you want to get tags from a specific category, like "1girl" or "solo".
- **Tags to Remove (Post)**: This remove the tags you define (this should be separated by commas e.g: 1girl,solo,short_hair) from the result query. This is useful if you want to remove tags that are too generic, like "1girl" or "solo". You can also use * with any tag to remove every tags which contains the related word. e.g: *hair will remove every tag that contains the word "hair".
- **Mature Rating**: This sets the mature rating of the booru. This is useful if you want to get only SFW or NSFW tags. It only works on supported boorus (right now it has been tested only on Gelbooru).
- **Remove Bad Tags**: This remove tags that you usually don't need (watermarks,text,censor)
- **Shuffle Tags**: This shuffle the tags before adding them to the text.
- **Convert** "\_" to Spaces": This convert \_ to spaces in the tags.
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

## How to use (RanbooruX)
See `usage.md` for examples.

### Bundled processing scripts
- `Comments` (now bundled): removes `#`, `//`, and `/* */` comments from prompts and negative prompts before other scripts run. It is shipped inside this extension (`scripts/comments.py`) so Forge/A1111 will load it automatically with RanbooruX enabled.

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

## Changelog
### 1.8 (Fork)
- Renamed to RanbooruX; cleaned UI
- ControlNet integration (external_code + automatic p.script_args fallback)
- Requests caching via `requests-cache`
- Updated background/color options and sorting

## Known Issues
- The chaos mode and negative mode can return an error when using a batch size greater than 1 combined with a batch count greater than 1. Rerunning the batch usually fixes the issue.
- "sd-dynamic-prompts" creates problems with the multiple prompts option. Disabling the extension is the only solution for now.
- Right now to run the img2img the extension creates an img with 1 step before creating the actual image. I don't know how to fix this, if someone want to help me with this I'd be grateful.
- Send to controlnet needs an dummy image to work.

## Found an issue?  
If you found an issue with the extension, please report it in the issues section of this repository.  
Special thanks to [TheGameratorT](https://github.com/TheGameratorT), [SmashinFries](https://github.com/SmashinFries), and [w-e-w](https://github.com/w-e-w) for contributing.

## Check out my other scripts
- [Ranbooru for ComfyUI](https://github.com/Inzaniak/comfyui-ranbooru)
- [Workflow](https://github.com/Inzaniak/sd-webui-workflow)

---
## Made by Inzaniak
![Alt text](pics/logo.png) 


If you'd like to support my work feel free to check out my Patreon: https://www.patreon.com/Inzaniak

Also check my other links:
- **Personal Website**: https://inzaniak.github.io 
- **Deviant Art**: https://www.deviantart.com/inzaniak
- **CivitAI**: https://civitai.com/user/Inzaniak/models
