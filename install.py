import os
import launch

req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
if os.path.exists(req_path):
    try:
        launch.run_pip(f"install -r \"{req_path}\"", "sd-webui-ranbooruX requirements")
    except Exception as e:
        print(f"[Ranbooru] Warning: failed to install requirements: {e}")
