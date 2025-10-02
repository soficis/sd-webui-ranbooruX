# RanbooruX Architecture

## Overview

RanbooruX is a Stable Diffusion WebUI extension that enhances image generation by fetching reference images from various booru sites (Danbooru, Gelbooru, etc.) and using them as input for img2img processing. The extension integrates deeply with the WebUI's processing pipeline, providing a two-pass workflow: initial txt2img generation followed by img2img refinement using fetched booru images.

Key features:

- Multi-booru support with standardized API interfaces
- Advanced prompt processing and tag manipulation
- ControlNet integration for image conditioning
- ADetailer integration for face/character enhancement
- Caching system for API requests
- Comprehensive UI for configuration

## Architecture Components

### 1. Booru API Layer

**Purpose**: Abstract interface for fetching images and metadata from various booru sites.

**Components**:

- `Booru` (base class): Handles HTTP requests, response parsing, and post standardization
- Site-specific subclasses: `Danbooru`, `Gelbooru`, `Rule34`, `Safebooru`, `Konachan`, `Yandere`, `AIBooru`, `e621`, `XBooru`
- `BooruError`: Custom exception for API failures

**Key Methods**:

- `_fetch_data()`: HTTP requests with caching and error handling
- `_standardize_post()`: Normalizes API responses into consistent format
- `get_posts()`: Fetches posts based on tags, ratings, and pagination

**Data Flow**: User tags → API query → Standardized post objects with image URLs and metadata

### 2. Main Script Class (`Script`)

**Purpose**: Core extension logic that hooks into WebUI's processing pipeline.

**Inheritance**: `scripts.Script` (WebUI base class)

**Key Hooks**:

- `before_process()`: Pre-generation setup, image fetching, prompt processing
- `postprocess()`: Post-generation img2img processing and ADetailer integration
- `ui()`: Gradio UI component creation

**Major Methods**:

- `_fetch_booru_posts()`: Orchestrates booru API calls
- `_select_posts()`: Applies sorting and selection logic
- `_fetch_images()`: Downloads and processes reference images
- `_process_single_prompt()`: Tag manipulation and prompt generation
- `_prepare_img2img_pass()`: Sets up two-pass workflow
- `_run_adetailer_on_img2img()`: Manual ADetailer execution

### 3. Image Processing Pipeline

**Purpose**: Handles image manipulation, resizing, and format conversion.

**Key Functions**:

- `resize_image()`: Aspect-ratio aware resizing with cropping options
- `check_orientation()`: Determines optimal dimensions based on image aspect ratio
- Image format utilities: PIL ↔ NumPy conversion, RGB normalization

**Integration Points**:

- Deepbooru tagging for automatic tag generation
- ControlNet unit configuration for image conditioning
- ADetailer preprocessing for face detection

### 4. ADetailer Integration Layer

**Purpose**: Provides face/character enhancement capabilities.

**Key Methods**:

- `_prepare_adetailer_for_img2img()`: Sets up ADetailer for post-img2img processing
- `_run_adetailer_on_img2img()`: Executes ADetailer on processed images
- `_patch_adetailer_directly()`: Forces ADetailer to use correct image references
- Guard mechanisms: Prevents premature or duplicate ADetailer execution

**Challenges Addressed**:

- Timing issues between txt2img and img2img passes
- Image reference consistency across processing stages
- Extension compatibility and hook ordering

### 5. UI Layer (Gradio)

**Purpose**: User interface for configuration and control.

**Components**:

- Accordion-based organization with collapsible sections
- Dropdowns for booru selection and rating filters
- Sliders for pagination, tag limits, and processing parameters
- Text areas for tag input and file selection
- Checkboxes for various processing options

**Dynamic Elements**:

- Rating options change based on selected booru
- File browser integration for tag files
- Real-time validation and feedback

### 6. Caching and State Management

**Purpose**: Optimizes performance and maintains processing state.

**Components**:

- `requests_cache`: HTTP response caching for booru APIs
- Instance-level caching: `_cached_posts`, `_last_search_key`
- Processing guards: Prevent duplicate execution and race conditions
- State flags: Track processing phases and completion status

**Key Attributes**:

- `_ranbooru_workflow_complete`: Prevents duplicate postprocess calls
- `_ranbooru_img2img_started`: Guards against re-entrant img2img
- `_current_processing_object`: Tracks active processing context

### 7. LoRAnado Subsystem

**Purpose**: Automated LoRA (Low-Rank Adaptation) selection and application.

**Key Methods**:

- `_apply_loranado()`: Random LoRA selection from subfolders
- Weight randomization within configured ranges
- Prompt injection for LoRA activation

## Data Flow

1. **User Input** → UI components collect configuration
2. **Pre-Processing** → `before_process()` validates and fetches booru data
3. **Image Fetch** → Download and cache reference images
4. **Prompt Generation** → Process tags, apply filters, generate final prompts
5. **Initial Generation** → WebUI txt2img with modified prompts
6. **Img2Img Processing** → `postprocess()` applies reference images via img2img
7. **ADetailer Enhancement** → Face/character processing on final results
8. **Result Integration** → Update processed object for UI display

## Dependencies

### Core Dependencies

- `requests`: HTTP client for booru APIs
- `PIL` (Pillow): Image processing and manipulation
- `numpy`: Array operations for image data
- `gradio`: UI framework
- `requests_cache`: HTTP caching

### WebUI Modules

- `modules.processing`: Core processing classes
- `modules.shared`: Global state and configuration
- `modules.scripts`: Extension framework
- `modules.ui_components`: UI building blocks
- `modules.deepbooru`: Automatic tagging
- `modules.sd_hijack`: Model manipulation

### Optional/Conditional

- ControlNet external_code API
- ADetailer extension hooks
- LoRA directory access

## Configuration and State

### User Configuration

- Booru selection and API parameters
- Tag processing rules and filters
- Image processing options (resize, crop, deepbooru)
- ControlNet and ADetailer settings
- Caching and performance options

### Runtime State

- Cached posts and images
- Processing guards and completion flags
- Temporary file paths and cleanup tracking
- Extension compatibility patches

### File Structure

```text
ranbooruX/
├── scripts/
│   ├── ranbooru.py          # Main extension script
│   ├── controlnet.py        # Modified ControlNet script for compatibility
│   └── adetailer/           # ADetailer integration
├── user/                    # User data directory
│   ├── search/              # Tag search files
│   └── remove/              # Tag removal files
├── requirements.txt         # Python dependencies
└── README.md               # Documentation
```

## Extension Points and Hooks

### WebUI Integration

- `before_process`: Pre-generation setup
- `postprocess`: Post-generation processing
- `ui`: Interface creation
- `process_batch*`: Batch processing hooks

### ADetailer Compatibility

- Script runner patching
- Image reference overriding
- Processing guard management
- Manual execution triggers

### ControlNet Integration

- Unit configuration via external_code API
- Script args manipulation fallback
- Image preprocessing for conditioning

## Error Handling and Resilience

### API Failures

- Timeout handling with configurable limits
- Fallback to cached data when available
- Graceful degradation for missing images

### Processing Errors

- Guard mechanisms prevent infinite loops
- Cleanup routines ensure state consistency
- Exception isolation prevents cascade failures

### Compatibility Issues

- Version detection and feature availability checks
- Fallback mechanisms for missing dependencies
- Extension ordering and hook priority management

## Performance Considerations

### Caching Strategy

- HTTP response caching reduces API load
- Image and post data caching for repeated use
- Memory management for large image sets

### Processing Optimization

- Batch size management for memory efficiency
- Asynchronous image downloading
- Selective processing based on configuration

### Resource Management

- Temporary file cleanup
- Memory leak prevention in long-running sessions
- CPU/GPU utilization balancing


## Detailed analysis: scripts/ranbooru.py

This section drills into the implementation details of `scripts/ranbooru.py`. It explains the two-pass workflow, the guard flags used to avoid duplicate runs, how ADetailer is coordinated, and recommended tests and improvements.

### Contract
- Inputs: a `StableDiffusionProcessing` object (`p`) during `before_process` and `postprocess` stages with typical WebUI fields (prompt, negative_prompt, steps, cfg_scale, batch_size, n_iter, seed, script_args, etc.).
- Outputs: mutates the `processed` object in `postprocess` so UI and other extensions see final img2img results (replaces `processed.images`, `prompt`, `infotexts`, seeds, sizes, and related lists).
- Error modes: network/API failures, image fetch failures, exceptions from ADetailer or ControlNet, and race conditions from concurrent hook invocations.

### Two-pass workflow (precise flow)
1. before_process(p, *args)
	- Fast-paths: if this is an internal img2img call (`_ranbooru_internal_img2img`), seeds are initialized and the call returns quickly.
	- Triple-layer guards applied to stop re-entry: instance flag `_ranbooru_processing_<id>`, class flag `_ranbooru_global_processing`, and processing-object flag `_ranbooru_already_processing`.
	- Fetch/select booru posts and download reference images. Cache results on the Script instance (`_cached_posts`, `_last_search_key`, `last_img`).
	- If `use_img2img` is enabled, call `_prepare_img2img_pass()` which: reduces steps and cfg for an initial pass, swaps prompt to a minimal placeholder, forces do-not-save, redirects outpath to a temporary directory, sets batch size to 1, and marks the initial-pass via `_ranbooru_initial_pass`.

2. Main generation (initial txt2img pass)
	- ADetailer is aggressively blocked during this pass via `_early_adetailer_protection()` and several setter flags to prevent it running on the low-quality intermediate results.

3. postprocess(p, processed, *args)
	- Validates state and checks flags (`_ranbooru_img2img_started`, `_ranbooru_manual_adetailer_active`, etc.). Sets `_ranbooru_img2img_started` early to avoid duplicates.
	- Restores ADetailer protections, prepares images (resize/crop), and runs a dedicated img2img processing job per image (using StableDiffusionProcessingImg2Img, marked internal so before_process seed-fast-path applies).
	- Collects `all_img2img_results` and then performs an aggressive in-place update of `processed` and any cached references other extensions might hold (clearing and extending lists rather than swapping objects when possible).
	- Attempts to run ADetailer manually on the img2img results using `_run_adetailer_on_img2img()`. This method tries multiple strategies (temp processed objects, direct script invocation, pipeline calls, function monkey-patches, numpy->PIL conversion hooks, and manual save).
	- Ensures cleanup via `_cleanup_after_run()` and clears guards in the `finally` block. The code now marks processing complete (important: `processed._ranbooru_workflow_complete` is set on all exits to avoid re-processing on error paths).

### Key guard flags (what they mean and where set/cleared)
- self._ranbooru_processing_<id> (instance): set in `before_process`, cleared in `postprocess` finally block.
- Script.__class__._ranbooru_global_processing (class): indicates any RanbooruX activity is in-flight; set in `before_process`, cleared at end of `postprocess` (with a short sleep to reduce races).
- p._ranbooru_already_processing (processing object): per-request guard to prevent the same processing object from being re-used concurrently; set in `before_process`.
- p._ranbooru_img2img_started (processing object): set in `postprocess` when the img2img sequence starts, preventing duplicate img2img attempts.
- processed._ranbooru_workflow_complete: set after finishing (or on exception) in `postprocess` to ensure other hooks skip re-processing the same result.
- _ranbooru_initial_pass / _ranbooru_intermediate_results: used to mark and detect initial cheap pass results vs final img2img results.
- _ranbooru_manual_adetailer_active / _ranbooru_manual_adetailer_complete: used to coordinate manual ADetailer runs and avoid recursive re-entry.

### ADetailer coordination (summary of approach)
- Initial pass: ADetailer scripts are removed/disabled from runners or blocked via multiple guards so they don't run on low-quality intermediate images.
- After img2img: RanbooruX attempts a robust manual ADetailer run per-image. The code converts numpy arrays to PIL where necessary, constructs temporary `processed` objects, and calls ADetailer's `postprocess_image` or `postprocess` methods. If needed it monkey-patches ADetailer modules or WebUI functions to ensure ADetailer consumes the correct images.
- If manual ADetailer succeeds, `processed.images` and `img2img_results` are updated with ADetailer outputs and `_ranbooru_manual_adetailer_complete` is set.

### Notable edge cases and failure modes
- Partial image fetch failures: `_fetch_images` may return None entries; `postprocess` fills gaps using first valid image or aborts when none available.
- Exceptions inside img2img loop: the `finally` block runs `_cleanup_after_run()` and clears guards; the script now ensures `processed._ranbooru_workflow_complete` is set even on exceptions to prevent retries.
- ADetailer detection/version quirks: RanbooruX uses multiple detection and patching strategies — differences across ADetailer versions could still cause missed hooks.
- Race conditions: clearing class-level guards immediately can race with other threads/hooks; the code uses a short sleep (0.1s) before clearing `_ranbooru_global_processing` to reduce but not fully eliminate races.

### Recommended tests (minimal reproducer + edge cases)
1. Happy-path manual test: run a two-pass generation with `use_img2img=True` and ADetailer installed — confirm final UI shows img2img (and ADetailer-processed) images and that only one txt2img initial pass ran.
2. Exception path: inject an exception into the img2img inner loop (raise inside one image processing) and confirm `processed._ranbooru_workflow_complete` is set and no duplicate generations occur afterwards.
3. Missing ADetailer: run without ADetailer installed and verify RanbooruX gracefully skips manual ADetailer and still shows img2img results.
4. Partial fetch: simulate one invalid image URL in a batch and verify fill-in logic uses fallback images and the pipeline completes.
5. Concurrency test: fire two rapid sequential runs and assert class-level guard blocks the second until the first completes.

### Small, low-risk improvements to consider
- Make guard clearing atomic with a single method that sets/clears a small state object instead of deleting attributes (reduces rare AttributeError races).
- Replace sleeps with a well-documented rely-on-order approach (for example, use an incrementing generation id and check equality) to avoid timing-based races.
- Expose a debug-mode flag that dumps the key guard flag states into logs or a small UI element for easier reproduction.
- Add lightweight unit tests or an integration test harness that can run `before_process` and `postprocess` with mocked `StableDiffusionProcessing` objects and fake ADetailer scripts.

### Requirements coverage (quick checklist)
- Two-pass workflow implemented: Done
- Guard flags to avoid duplicate runs: Done (multiple levels)
- Ensure processed is marked complete on errors: Done (set in postprocess finally)
- Manual ADetailer execution attempt: Done (multiple strategies)
