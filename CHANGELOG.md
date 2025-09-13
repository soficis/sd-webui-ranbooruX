# CHANGELOG - RanbooruX

This document outlines the principal changes in **RanbooruX**, a feature-rich, stability-focused fork of the original Ranbooru project. For usage examples and workflow diagrams, please see the [Usage Guide](usage.md).

---

## v1.0.0 - Initial RanbooruX Release

This inaugural release marks the official fork of Ranbooru, introducing a comprehensive architectural overhaul, new features, and critical bug fixes for a more stable and powerful experience.

### ✨ Features
- **Stable ControlNet Integration**: Bundled a self-contained ControlNet module (`sd_forge_controlnet`) to ensure a stable, long-term compatible API for sending images directly to ControlNet, especially for SD Forge users.
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
RanbooruX began as an extensive refactor of Ranbooru, with a primary focus on fixing critical `img2img` and `ControlNet` integration bugs. It has since evolved to include a reorganized codebase, a cleaner UI, and compatibility enhancements for both **Forge** and **AUTOMATIC1111** WebUI environments.

---

## Key Changes & Rationale

### 1. Refactor and Reorganization
The codebase was restructured to improve clarity, maintainability, and ease of future development. This included updating module and package layouts to better support bundled dependencies and ensure Forge compatibility.

### 2. Img2Img Fixes
- **Stabilized Pipeline**: The original Ranbooru `img2img` flow, which required a dummy one-step seed image, has been completely repaired. RanbooruX now reliably uses the source image without generating unnecessary placeholders.
- **Enhanced Controls**: Added UI options to control denoising strength and reuse the last fetched image as a source for batch runs.

### 3. ControlNet Integration
- **Robust Integration Path**: RanbooruX now uses a robust integration path that prefers Forge/A1111 external API helpers when available and automatically falls back to a `p.script_args`-based method when they are not. This ensures maximum compatibility.
- **Bundled Scripts**: The extension includes a bundled `sd_forge_controlnet` copy and provides documented steps to overwrite host ControlNet scripts if the host environment fails to pass `img2img` inputs to ControlNet Unit 0 by default.

### 4. UI/UX Enhancements
- The user interface was reorganized to present options more clearly.
- Controls for mixing prompts, chaos/negative modes, background/color forcing, and LoRAnado were consolidated for a more intuitive user experience.

### 5. Bundled Helper Scripts
- Common helper scripts like `Comments` (for prompt comment stripping) are now bundled directly within the `scripts/` directory, ensuring they load reliably whenever RanbooruX is enabled.

### 6. Performance
- **Request Caching**: Integrated `requests-cache` to reduce redundant API calls to booru sites, which minimizes rate-limiting issues and speeds up repeated queries.

---

## Migration Notes
If you are migrating from the original Ranbooru and rely on `img2img` or `ControlNet` features, RanbooruX is designed as a drop-in replacement. Review the optional ControlNet overwrite steps in the [README.md](README.md) if your Forge build does not correctly pass `img2img` inputs to ControlNet Unit 0.

---

## Technical Details

### Example Log Lines
RanbooruX logs which ControlNet path it used at runtime. You will see one of the following lines in your WebUI console:

-   **External API Path (Preferred)**:
    ```
    [R Before] ControlNet configured via external_code.
    ```
-   **Fallback Path (For Forge builds lacking programmatic helpers)**:
    ```
    [R Before] ControlNet using fallback p.script_args hack.
    ```

### Manual Verification Steps
To verify that `img2img` and `ControlNet` are working correctly in a Forge environment, follow these steps:
1.  **Setup**: Install RanbooruX in your `extensions` folder and ensure all dependencies from `requirements.txt` are installed.
2.  **Img2Img Test**:
    -   Open the RanbooruX panel and check `Use img2img`.
    -   Run a small batch (size 1) and confirm that it produces a new image from the booru source without generating a placeholder image first.
3.  **ControlNet Test**:
    -   Enable `Send to ControlNet` alongside `Use img2img`.
    -   Check the logs for one of the two messages shown above to confirm which integration path was used.

For a complete list of known issues and limitations, please refer to the main [README.md](README.md).
