import os

import launch

ext_root = os.path.dirname(__file__)


def _install_req(path, desc):
    if os.path.exists(path):
        try:
            launch.run_pip(f'install -r "{path}"', desc)
        except Exception as e:
            print(f"[RanbooruX] Warning: failed to install {desc}: {e}")


_install_req(os.path.join(ext_root, "requirements.txt"), "RanbooruX requirements")
