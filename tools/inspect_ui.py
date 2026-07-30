import importlib
import os
import sys
import types

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Create mock environment similar to tests/conftest.py
modules_pkg = types.ModuleType("modules")
modules_pkg.__path__ = []
sys.modules["modules"] = modules_pkg

scripts_mod = types.ModuleType("modules.scripts")


class DummyScript:
    def elem_id(self, name):
        return name


scripts_mod.Script = DummyScript
scripts_mod.basedir = lambda: "."
sys.modules["modules.scripts"] = scripts_mod

processing_mod = types.ModuleType("modules.processing")
processing_mod.process_images = lambda *a, **kw: None
processing_mod.StableDiffusionProcessingImg2Img = type("PImg2Img", (), {})
processing_mod.StableDiffusionProcessing = type("P", (), {})
sys.modules["modules.processing"] = processing_mod

shared_mod = types.ModuleType("modules.shared")
shared_mod.state = types.SimpleNamespace()
sys.modules["modules.shared"] = shared_mod

sd_hijack_mod = types.ModuleType("modules.sd_hijack")
sd_hijack_mod.model_hijack = types.SimpleNamespace(embedding_db=None)
sys.modules["modules.sd_hijack"] = sd_hijack_mod

ui_components_mod = types.ModuleType("modules.ui_components")


class DummyAccordion:
    def __init__(self, *args, **kwargs):
        self.label = kwargs.get("label", "")
        self.elem_id = kwargs.get("elem_id", "")

    def __enter__(self):
        # We need this to return a component representation
        c = ComponentInfo("InputAccordion", label=self.label, default=False)
        components.append(c)
        return c

    def __exit__(self, exc_type, exc, tb):
        return False


ui_components_mod.InputAccordion = DummyAccordion
sys.modules["modules.ui_components"] = ui_components_mod

# Intercept Gradio Component Creations
components = []


class ComponentInfo:
    def __init__(self, type_name, label="", default=None):
        self.type_name = type_name
        self.label = label
        self.default = default


class InterceptComponent:
    def __init__(self, *args, **kwargs):
        # Determine label and default value
        label = kwargs.get("label", "")
        if not label and args:
            # Maybe label is positional
            label = args[0]
        default = kwargs.get("value", None)

        self.label = label
        self.default = default

        # Infer type name from class being instantiated
        type_name = self.__class__.__name__
        c = ComponentInfo(type_name, label=label, default=default)
        components.append(c)

    def change(self, *args, **kwargs):
        return self

    def click(self, *args, **kwargs):
        return self

    def upload(self, *args, **kwargs):
        return self

    def select(self, *args, **kwargs):
        return self


gradio_mod = types.ModuleType("gradio")
gradio_mod.__version__ = "3.41.2"
gradio_mod.update = lambda **kwargs: kwargs

for name in (
    "Checkbox",
    "Textbox",
    "Button",
    "Markdown",
    "Slider",
    "Radio",
    "Dropdown",
    "File",
    "DownloadButton",
    "State",
):
    # Create subclass dynamically so type_name matches
    cls = type(name, (InterceptComponent,), {})
    setattr(gradio_mod, name, cls)


class InterceptContext:
    def __init__(self, *args, **kwargs):
        self.label = kwargs.get("label", "")
        self.type_name = self.__class__.__name__

    def __enter__(self):
        # Containers themselves are not in the 62-component positional return list
        # only leaf/interactive components, but let's return a dummy
        return InterceptComponent(label=self.label)

    def __exit__(self, exc_type, exc, tb):
        return False


for name in ("Group", "Row", "Column", "Accordion", "Box"):
    cls = type(name, (InterceptContext,), {})
    setattr(gradio_mod, name, cls)

sys.modules["gradio"] = gradio_mod

# Stub requests/cache/numpy/PIL
sys.modules["requests_cache"] = types.ModuleType("requests_cache")
requests_mod = types.ModuleType("requests")
requests_mod.get = lambda *a, **kw: None
sys.modules["requests"] = requests_mod
sys.modules["numpy"] = types.ModuleType("numpy")
sys.modules["PIL"] = types.ModuleType("PIL")
sys.modules["PIL.Image"] = types.ModuleType("PIL.Image")

ranbooru = importlib.import_module("scripts.ranbooru")
script = ranbooru.Script()
# We intercept the returned components directly to preserve their names in scripts/ranbooru.py
returned_components = script.ui(is_img2img=False)

# Write contract to docs/handoff/UI_ARGUMENT_CONTRACT.md
output_path = "docs/handoff/UI_ARGUMENT_CONTRACT.md"
os.makedirs(os.path.dirname(output_path), exist_ok=True)

# We map components back to their indices and variable names
# The return statement from scripts/ranbooru.py has 64 items:
variable_names = [
    "enabled",
    "tags",
    "booru",
    "gelbooru_api_key",
    "gelbooru_user_id",
    "gelbooru_compat_base_url",
    "remove_bad_tags",
    "max_pages",
    "change_dash",
    "same_prompt",
    "fringe_benefits",
    "remove_tags",
    "use_img2img",
    "denoising",
    "use_last_img",
    "change_background",
    "change_color",
    "shuffle_tags",
    "post_id",
    "mix_prompt",
    "mix_amount",
    "chaos_mode",
    "chaos_amount",
    "limit_tags",
    "max_tags",
    "sorting_order",
    "mature_rating",
    "lora_folder",
    "lora_amount",
    "lora_min",
    "lora_max",
    "lora_enabled",
    "lora_custom_weights",
    "lora_lock_prev",
    "use_ip",
    "use_search_txt",
    "use_remove_txt",
    "choose_search_txt",
    "choose_remove_txt",
    "search_refresh_btn",
    "remove_refresh_btn",
    "crop_center",
    "enable_adetailer_support",
    "use_same_seed",
    "reuse_cached_posts",
    "use_cache",
    "log_prompt_sources",
    "remove_artist_tags",
    "remove_character_tags",
    "remove_clothing_tags",
    "remove_text_tags",
    "restrict_subject_tags",
    "remove_furry_tags",
    "remove_headwear_tags",
    "remove_girl_suffix_tags",
    "preserve_hair_eye_colors",
    "remove_series_tags",
    "use_tag_catalog",
    "catalog_path",
    "lora_auto_detect_pony",
    "lora_detected_loras",
    "lora_blacklist",
]

with open(output_path, "w", encoding="utf-8") as f:
    f.write("# RanbooruX UI Argument Contract\n\n")
    f.write(
        "This document defines the frozen contract for the 62 positional arguments returned by `Script.ui()` and received by `before_process() / process()`.\n\n"
    )
    f.write("| Index | Variable Name | Component Type | Label | Default Value |\n")
    f.write("|---|---|---|---|---|\n")

    # We match each returned component to get its details.
    # Note: returned_components lists the objects in order. We can query their intercepted properties.
    for idx, (var_name, comp) in enumerate(zip(variable_names, returned_components)):
        # Inspect properties from the comp object
        # Since it could be a SimpleNamespace (for InputAccordion) or an InterceptComponent
        label = getattr(comp, "label", "")
        # Get class name of the mock component
        comp_type = comp.__class__.__name__
        if comp_type == "SimpleNamespace" and var_name == "enabled":
            comp_type = "InputAccordion"
            label = "RanbooruX"
            default = "False"
        else:
            default = getattr(comp, "default", None)

        f.write(f"| {idx} | `{var_name}` | {comp_type} | {label} | {default} |\n")

print(f"Contract successfully written to {output_path}")
