# CHANGELOG - RanbooruX (fork of Ranbooru)

This file describes the principal changes introduced in RanbooruX compared to the original Ranbooru project included in `sd-webui-ranbooru-main/`.

## Overview
RanbooruX is an extensive refactor and compatibility-focused fork of Ranbooru. Changes include fixes to image flows, ControlNet integration, improved UI, and packaging adjustments to work with both Forge and AUTOMATIC1111 WebUI environments.

## Key changes and rationale
- Refactor and reorganization
  - The codebase has been reorganized for clarity and maintainability. Module and package layouts were updated to make bundled ControlNet integration and Forge compatibility easier to maintain.

- Img2Img fixes
  - The original Ranbooru had a brittle Img2Img flow that required a dummy one-step seed image to be created before the actual Img2Img pass. RanbooruX repairs and stabilizes the Img2Img pipeline so the source image is used reliably without unnecessary placeholder generations.
  - Added options and UI hooks to control denoising strength and reuse the last image as source for batch runs.

- ControlNet fixes and fallbacks
  - RanbooruX provides a robust ControlNet integration path that prefers Forge/A1111 external API helpers when present, and falls back to a p.script_args-based method when the host does not expose programmatic helpers.
  - The extension includes a bundled `sd_forge_controlnet` copy and documented steps to overwrite host ControlNet scripts if the host does not pass Img2Img inputs to ControlNet Unit 0 by default.
  - This ensures sending images to ControlNet Unit 0 (for conditioning) works in more Forge builds where it previously failed.

- UI changes
  - The UI was cleaned and reorganized to present options more clearly, including controls for mixing prompts, chaos/negative modes, background/color forcing, and LoRAnado.

- Bundled helper scripts
  - Included helpful scripts such as `Comments` (prompt comment stripping) inside `scripts/` so they load reliably with RanbooruX enabled.

- Requests caching
  - Integrated `requests-cache` to reduce API calls to booru sites and minimize rate-limiting problems.

## Notable code differences (examples)
- `scripts/comments.py`
  - The RanbooruX bundled version improves robustness when handling prompt fields that may be lists (e.g. `all_prompts`) and avoids errors that occur when `hr_prompt` or other fields are missing or of unexpected types.

- `sd_forge_controlnet/scripts/controlnet.py` (optional overwrite)
  - RanbooruX ships a modified ControlNet script which can be used to enable full Img2Img + ControlNet behavior on Forge builds that otherwise don't pass the Img2Img source image to ControlNet units.

## Migration notes
- If you use the original Ranbooru and depend on Img2Img or ControlNet features, RanbooruX is intended as a drop-in replacement. Review the optional ControlNet overwrite steps in `README.md` if your Forge build does not pass Img2Img inputs to ControlNet Unit 0.

## Known limitations and compatibility
- Some edge cases remain (e.g., chaos mode with certain batch sizes). See `README.md` for the current list of known issues.

---

For a quick summary of smaller commits and UI tweaks, see the `README.md` at the project root (RanbooruX), which contains a short changelog entry for the fork release.

## File-level highlights (concise diffs)
Below are the most relevant file-level changes with short descriptions of what changed. These are not full diffs but are targeted notes to help reviewers locate edits.

- `scripts/ranbooru.py`
  - Reworked request and image handling paths; improved header/user-agent usage and caching calls (added `requests_cache.install_cache(...)`).
  - Added explicit checks and environment variable fallbacks for `SD_FORGE_CONTROLNET_PATH` / `RANBOORUX_CN_PATH` to locate a compatible ControlNet install.

- `scripts/comments.py`
  - Replaced the original single-string-only stripping logic with a version that safely handles lists (`all_prompts`) and avoids attribute errors when optional fields are missing.

- `sd_forge_controlnet/` (bundled copy)
  - Added to the repo to provide a compatible ControlNet integration path; includes a modified `scripts/controlnet.py` that works with Forge Img2Img inputs or can be used as an overwrite when necessary.

- `README.md` / `usage.md`
  - Documentation updated to explain the fork, ControlNet fallback behavior, and provide optional overwrite steps for Forge users.

## Example log lines
RanbooruX logs which ControlNet path it used at runtime. Example lines you may see in the WebUI log:

- When the external API path (preferred) is used:

  [R Before] ControlNet configured via external_code.

- When the fallback p.script_args path is used (Forge builds lacking programmatic helpers):

  [R Before] ControlNet using fallback p.script_args hack.

These lines are concise markers to help debug which integration path was taken.

## Manual verification steps (Img2Img and ControlNet on Forge)
Follow these short steps to verify Img2Img and ControlNet behavior on a Forge build.

1. Setup
   - Install RanbooruX into your WebUI `extensions` folder (or copy the entire extension directory into `webui/extensions-builtin` for Forge testing).
   - Ensure dependencies are installed (run `install.py` or `pip install -r requirements.txt`).
   - If you have a separate Forge ControlNet, note its path and set `SD_FORGE_CONTROLNET_PATH` or `RANBOORUX_CN_PATH` environment variable to that folder before starting the WebUI.

2. Quick Img2Img smoke test
   - Open the RanbooruX panel and enable `Use img2img`.
   - Choose a booru and enable `Send to ControlNet` if you want to test both together.
   - Run a small batch (batch size 1) and watch the WebUI logs. Successful Img2Img should produce a new image using the source image from the booru without an extra placeholder one-step generation.

3. Verify ControlNet integration
   - In the logs look for either of the example lines above. If you see `ControlNet configured via external_code.`, the external API path was used.
   - If you see `ControlNet using fallback p.script_args hack.`, the fallback path was taken. Both paths should still produce a conditioned generation; the fallback is intended to make the feature work when the host ControlNet is limited.

4. Optional: Force the bundled ControlNet overwrite
   - If the fallback path fails for your Forge build, back up your host `webui\extensions-builtin\sd_forge_controlnet\scripts\controlnet.py` and copy the bundled file from `sd-webui-ranbooruX\sd_forge_controlnet\scripts\controlnet.py` into that location, then restart the WebUI.
   - Re-run the test in step 2 and confirm the generation behavior and the log lines.

5. Notes and troubleshooting
   - If Img2Img still creates a one-step placeholder image, check for conflicting extensions (e.g., `sd-dynamic-prompts`) and try disabling them.
   - Use a minimal batch and reduced model complexity while testing to shorten iteration time.

---

End of changelog.
