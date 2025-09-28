# CHANGELOG - RanbooruX

This document outlines the principal changes in **RanbooruX**, a feature-rich, stability-focused fork of the original Ranbooru project. For usage examples and workflow diagrams, please see the [Usage Guide](usage.md).

---

## adetailer-branch (WIP)

### Added
- Automatic ADetailer post-processing after every RanbooruX Img2Img run, including ControlNet-assisted generations.
- Sequential batch pipeline that routes each image through ADetailer while preserving the original Img2Img result for comparison.
- Optional reuse of cached booru posts (disabled by default for always-fresh generations).
- New prompt hygiene toggles: stronger artist/character removal, clothing filtering, text/commentary filtering, and subject-count enforcement.
- Optional logging toggle that records prompts, seeds, and source posts to `user/logs/prompt_sources.txt`.

### Changed
- Added an explicit "Enable RanbooruX ADetailer support" toggle so the manual pipeline only runs when requested.
- Default generations now fetch fresh booru posts; enable the reuse toggle only when you want cached results.
- Beefed up artist/character removal heuristics to catch stubborn names, series tags, and metadata spam.
- Updated README and Usage Guide with fresh-fetch behavior, new filtering toggles, and the logging option.
- Highlighted the adetailer branch status and workflow expectations for new testers.

### Fixed
- Prevented initial txt2img warm-up frames from overwriting Img2Img outputs during ADetailer runs.
- Resolved cases where multi-image batches skipped ADetailer, ensuring every saved frame includes processed metadata.

## v1.1.0 - Stability and Performance Improvements

This release focuses on critical stability fixes, performance optimizations, and new user-friendly features to enhance the overall RanbooruX experience.

### ✨ New Features
- **Intelligent Image Caching**: Added automatic caching of fetched images and posts to improve performance and consistency. Images are reused for subsequent generations with identical search parameters, reducing API calls and generation time.
- **Force Refresh Feature**: Added `!refresh` tag support - append `!refresh` to your search tags (e.g., `1girl, solo, short_hair,!refresh`) to force fetch new images instead of using cached ones.
- **Enhanced URL Filtering**: Improved image URL validation to prevent failed fetches from external sites like Pixiv and Twitter that don't provide direct image access.
- **Comprehensive Documentation**: Updated usage guides with detailed explanations of new features, caching behavior, and troubleshooting tips.

### 🐛 Critical Bug Fixes
- **Fixed PerturbedAttentionGuidance Division by Zero**: Resolved crash caused by setting steps to 1 in Img2Img processing. Now uses minimum 2 steps to avoid division errors in Forge extensions.
- **Fixed Batch Processing Errors**: Completely rewrote Img2Img postprocessing to handle multiple images individually instead of attempting batch processing, resolving "bad number of images passed" runtime errors.
- **Fixed Single Image Generation**: Resolved IndexError crashes when generating single images with cached data from previous multi-image batches.
- **Fixed Variable Scoping Issues**: Fixed `UnboundLocalError` where `num_images_needed` variable was only defined in certain code paths, causing crashes when reusing cached images.
- **Fixed Syntax Errors**: Resolved missing parentheses that prevented the extension from loading in Forge.

### 🛠️ Performance & Reliability
- **Optimized Memory Usage**: Improved image processing pipeline to reduce memory overhead during batch operations.
- **Enhanced Error Handling**: Better error messages and graceful degradation when image processing fails.
- **Cache Management**: Automatic cache invalidation when search parameters change (booru, tags, post ID, rating, sorting order).

### 📚 Documentation Updates
- **Image Caching Section**: Added comprehensive documentation explaining automatic caching behavior and manual refresh options.
- **Troubleshooting Notes**: Added notes about bundled `comments.py` script not being required for all users.
- **Usage Examples**: Enhanced examples showing `!refresh` usage in different workflows.

---

## v1.0.0 - Initial RanbooruX Release

This inaugural release marks the official fork of Ranbooru, introducing a comprehensive architectural overhaul, new features, and critical bug fixes for a more stable and powerful experience.

### ✨ Features
- **Stable ControlNet Integration**: Included a modified ControlNet script (`scripts/controlnet.py`) to ensure a stable, long-term compatible API for sending images directly to ControlNet, especially for SD Forge users.
- **Advanced Prompt Controls**:
    - **Mix Prompts**: Combine tags from multiple random posts to generate complex and varied prompts.
    - **Chaos Mode**: Introduce controlled randomness by shuffling tags between positive and negative prompts.
    - **Tag Filtering**: Limit tag count by percentage or a maximum number, and use external files for managing tags to remove.
- **LoRAnado**: Automates the selection and application of multiple LoRAs from a specified subfolder, with configurable weights and locking for batch consistency.
- **Enhanced Batch Processing**: Added options to use the same prompt, source image (`img2img`/`ControlNet`), and seed across an entire batch for consistent outputs.
- **Photopea Integration**: Edit ControlNet input images directly within the WebUI using an integrated Photopea modal for precise, on-the-fly adjustments.

### 🐛 Bug Fixes
- **Corrected `img2img` Workflow**: The `img2img` pipeline was completely repaired, removing the need for a dummy one-step seed image and ensuring the source image is used reliably.
- **Robust API Error Handling**: Implemented proper `try...except` blocks and a custom `BooruError` to gracefully handle network timeouts, HTTP errors, and invalid API responses that previously caused silent failures.

### 🛠️ Refactoring & Performance
- **Complete Code Refactor**: The core `ranbooru.py` script was rewritten using an Object-Oriented architecture, introducing a base `Booru` class to abstract API logic, improve readability, and reduce code duplication.
- **Request Caching**: Integrated `requests-cache` to cache API responses, significantly speeding up repeated queries and reducing the risk of being rate-limited.
- **Improved Logging & Debugging**: Added consistent `[R] ...` logging throughout the script to make debugging easier.
- **UI Reorganization**: The user interface was cleaned up and consolidated for a more intuitive and user-friendly experience.

### ⚙️ Build & Dependencies
- **Modernized Installation**: Replaced the original hardcoded dependency check in `install.py` with a modern approach that reads from `requirements.txt`, allowing for version pinning and more reliable installations.

---

## Overview
RanbooruX began as an extensive refactor of Ranbooru, with a primary focus on fixing critical `img2img` and `ControlNet` integration bugs. Since its initial release, RanbooruX has evolved significantly with major stability improvements, including intelligent image caching, comprehensive error handling, and performance optimizations. The extension now provides a robust, production-ready experience for both **Forge** and **AUTOMATIC1111** WebUI environments.

---

## Key Changes & Rationale

### 1. Refactor and Reorganization
The codebase was restructured to improve clarity, maintainability, and ease of future development. This included updating module and package layouts to better support bundled dependencies and ensure Forge compatibility.

### 2. Img2Img Fixes

- Stabilized Pipeline: The original Ranbooru `img2img` flow, which required a dummy one-step seed image, has been completely repaired. RanbooruX now reliably uses the source image without generating unnecessary placeholders.
- Enhanced Controls: Added UI options to control denoising strength and reuse the last fetched image as a source for batch runs.
- Batch Processing Overhaul: Completely rewrote the postprocessing pipeline to handle multiple images individually, eliminating "bad number of images passed" runtime errors.

### 3. ControlNet Integration

- Robust Integration Path: RanbooruX now uses a robust integration path that prefers Forge/A1111 external API helpers when available and automatically falls back to a `p.script_args`-based method when they are not. This ensures maximum compatibility.
- Bundled Scripts: The extension includes a modified `controlnet.py` script and provides documented steps to overwrite host ControlNet scripts if the host environment fails to pass `img2img` inputs to ControlNet Unit 0 by default.

### 4. UI/UX Enhancements

- The user interface was reorganized to present options more clearly.
- Controls for mixing prompts, chaos/negative modes, background/color forcing, and LoRAnado were consolidated for a more intuitive user experience.

### 5. Bundled Helper Scripts

- Common helper scripts like `Comments` (for prompt comment stripping) are now bundled directly within the `scripts/` directory, ensuring they load reliably whenever RanbooruX is enabled. Note: While bundled, these scripts may not be required for all users depending on their workflow.

### 6. Performance & Stability Improvements

- Request Caching: Integrated `requests-cache` to reduce redundant API calls to booru sites, which minimizes rate-limiting issues and speeds up repeated queries.
- Intelligent Image Caching: Added automatic caching of fetched images and posts with smart cache invalidation based on search parameters.
- Force Refresh Feature: Added `!refresh` tag support to manually invalidate cache and force fresh image fetches.
- Enhanced Error Handling: Comprehensive error handling for variable scoping issues, division by zero errors, and batch size mismatches.
- URL Filtering: Improved image URL validation to prevent failed fetches from external sites that don't provide direct access.

### 7. Compatibility Fixes

- Forge Extension Compatibility: Fixed PerturbedAttentionGuidance division by zero errors by using minimum 2 steps instead of 1.
- Single Image Generation: Resolved IndexError crashes when generating single images with cached data.
- Syntax Error Fixes: Resolved missing parentheses and other syntax issues that prevented extension loading.

---

## Migration Notes

If you are migrating from the original Ranbooru and rely on `img2img` or `ControlNet` features, RanbooruX is designed as a drop-in replacement. Review the optional ControlNet overwrite steps in the [README.md](README.md) if your Forge build does not correctly pass `img2img` inputs to ControlNet Unit 0 by default.

### Upgrading from v1.0.0 to v1.1.0

Existing RanbooruX v1.0.0 users will automatically benefit from all stability improvements and new features upon updating. No configuration changes are required, but you may notice:

- Faster subsequent generations due to automatic image caching
- More reliable batch processing for multiple images
- Improved error handling with clearer error messages
- New `!refresh` option for forcing fresh image fetches

The extension is backward compatible and all existing workflows will continue to work as expected.

---

## Technical Details

### Example Log Lines

RanbooruX logs which ControlNet path it used at runtime. You will see one of the following lines in your WebUI console:

- **External API Path (Preferred)**:

  ```text
  [R Before] ControlNet configured via external_code.
  ```

- **Fallback Path (For Forge builds lacking programmatic helpers)**:

  ```text
  [R Before] ControlNet using fallback p.script_args hack.
  ```

### Manual Verification Steps

To verify that `img2img` and `ControlNet` are working correctly in a Forge environment, follow these steps:

1. **Setup**: Install RanbooruX in your `extensions` folder and ensure all dependencies from `requirements.txt` are installed.
2. **Img2Img Test**:
   - Open the RanbooruX panel and check `Use img2img`.
   - Run a small batch (size 1) and confirm that it produces a new image from the booru source without generating a placeholder image first.
3. **ControlNet Test**:
   - Enable `Send to ControlNet` alongside `Use img2img`.
   - Check the logs for one of the two messages shown above to confirm which integration path was used.

For a complete list of known issues and limitations, please refer to the main [README.md](README.md).


