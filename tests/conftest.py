import sys
import types

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--gradio-version",
        action="store",
        default="3",
        choices=["3", "4"],
        help="Stub Gradio major version for tests (3 or 4).",
    )


@pytest.fixture(autouse=True)
def stub_modules(tmp_path, request):
    gradio_version = request.config.getoption("--gradio-version")

    modules_pkg = types.ModuleType("modules")
    modules_pkg.__path__ = []  # treat as package for fromlist imports
    sys.modules["modules"] = modules_pkg

    scripts_mod = types.ModuleType("modules.scripts")

    class DummyScript:
        def __init__(self):
            pass

        def elem_id(self, name):
            return name

    base_dir = tmp_path / "ext"
    base_dir.mkdir(parents=True, exist_ok=True)
    bundled_catalog_dir = base_dir / "data" / "catalogs"
    bundled_catalog_dir.mkdir(parents=True, exist_ok=True)
    (bundled_catalog_dir / "danbooru_tags.csv").write_text(
        "tag,category,count,alias\n1girl,0,100,\nblonde_hair,0,50,\n",
        encoding="utf-8",
    )

    def basedir():
        return str(base_dir)

    scripts_mod.Script = DummyScript
    scripts_mod.basedir = basedir
    sys.modules["modules.scripts"] = scripts_mod

    processing_mod = types.ModuleType("modules.processing")

    def process_images(*args, **kwargs):  # pragma: no cover - placeholder
        return None

    processing_mod.process_images = process_images
    processing_mod.StableDiffusionProcessingImg2Img = type("PImg2Img", (), {})
    processing_mod.StableDiffusionProcessing = type("P", (), {})
    sys.modules["modules.processing"] = processing_mod

    shared_mod = types.ModuleType("modules.shared")
    shared_mod.state = types.SimpleNamespace()
    sys.modules["modules.shared"] = shared_mod

    sd_hijack_mod = types.ModuleType("modules.sd_hijack")
    sd_hijack_mod.model_hijack = types.SimpleNamespace(embedding_db=None)
    sys.modules["modules.sd_hijack"] = sd_hijack_mod
    modules_pkg.sd_hijack = sd_hijack_mod

    ui_components_mod = types.ModuleType("modules.ui_components")

    class DummyAccordion:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return types.SimpleNamespace()

        def __exit__(self, exc_type, exc, tb):
            return False

    ui_components_mod.InputAccordion = DummyAccordion
    sys.modules["modules.ui_components"] = ui_components_mod
    modules_pkg.ui_components = ui_components_mod

    gradio_mod = types.ModuleType("gradio")
    gradio_mod.__version__ = "4.0.0" if gradio_version == "4" else "3.41.2"

    class DummyComponent:
        def __init__(self, *args, **kwargs):
            pass

        def change(self, *args, **kwargs):
            return None

        def click(self, *args, **kwargs):
            return None

        def upload(self, *args, **kwargs):
            return None

        def select(self, *args, **kwargs):
            return None

    if gradio_version == "3":

        @staticmethod
        def _update(**kwargs):
            return kwargs

        DummyComponent.update = _update

    class DummyContext:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return DummyComponent()

        def __exit__(self, exc_type, exc, tb):
            return False

    for _name in (
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
        setattr(gradio_mod, _name, DummyComponent)
    for _name in ("Group", "Row", "Column", "Accordion", "Box"):
        setattr(gradio_mod, _name, DummyContext)

    def _gr_update(**kwargs):
        return kwargs

    gradio_mod.update = _gr_update
    sys.modules["gradio"] = gradio_mod

    requests_cache_mod = types.ModuleType("requests_cache")

    class _DummyPatcher:
        def __init__(self):
            self._installed = False

        def is_installed(self):
            return self._installed

    _patcher = _DummyPatcher()

    def install_cache(*args, **kwargs):
        _patcher._installed = True

    def uninstall_cache(*args, **kwargs):
        _patcher._installed = False

    requests_cache_mod.patcher = _patcher
    requests_cache_mod.install_cache = install_cache
    requests_cache_mod.uninstall_cache = uninstall_cache
    sys.modules["requests_cache"] = requests_cache_mod

    requests_mod = types.ModuleType("requests")

    class _DummyResponse:
        def __init__(self, payload=None):
            self._payload = payload if payload is not None else {}
            self.content = b""
            self.text = ""
            self.status_code = 200

        def json(self):
            return self._payload

        def raise_for_status(self):
            return None

    def _dummy_get(*args, **kwargs):
        return _DummyResponse({})

    requests_mod.get = _dummy_get
    requests_mod.post = _dummy_get
    requests_mod.put = _dummy_get
    requests_mod.delete = _dummy_get
    requests_mod.Response = _DummyResponse
    requests_mod.RequestException = Exception
    requests_mod.Session = lambda: types.SimpleNamespace(get=_dummy_get, post=_dummy_get)
    sys.modules["requests"] = requests_mod

    numpy_mod = types.ModuleType("numpy")
    sys.modules["numpy"] = numpy_mod

    pil_pkg = types.ModuleType("PIL")
    pil_image_mod = types.ModuleType("PIL.Image")

    class DummyImage:
        width = 1
        height = 1

        def resize(self, *args, **kwargs):
            return self

        def crop(self, *args, **kwargs):
            return self

    pil_image_mod.Image = DummyImage
    pil_image_mod.Resampling = types.SimpleNamespace(LANCZOS=1)
    pil_pkg.Image = pil_image_mod
    sys.modules["PIL"] = pil_pkg
    sys.modules["PIL.Image"] = pil_image_mod

    yield

    for name in [
        "modules.ui_components",
        "modules.sd_hijack",
        "modules.shared",
        "modules.processing",
        "modules.scripts",
        "modules",
        "scripts.ranbooru",
        "gradio",
        "requests_cache",
        "requests",
        "numpy",
        "PIL.Image",
        "PIL",
    ]:
        sys.modules.pop(name, None)


@pytest.fixture
def active_gradio_version(request):
    return request.config.getoption("--gradio-version")


@pytest.fixture
def stub_modules_without_model_hijack(stub_modules):
    modules_pkg = sys.modules.get("modules")
    if modules_pkg is not None and hasattr(modules_pkg, "sd_hijack"):
        delattr(modules_pkg, "sd_hijack")
    sys.modules.pop("modules.sd_hijack", None)
    sys.modules.pop("scripts.ranbooru", None)
    return True


@pytest.fixture
def stub_modules_without_inputaccordion(stub_modules):
    modules_pkg = sys.modules.get("modules")
    if modules_pkg is not None and hasattr(modules_pkg, "ui_components"):
        delattr(modules_pkg, "ui_components")
    sys.modules.pop("modules.ui_components", None)
    sys.modules.pop("scripts.ranbooru", None)
    return True
