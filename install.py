import os
import sys

import launch

ext_root = os.path.dirname(__file__)


def _install_req(path, desc):
    if os.path.exists(path):
        try:
            # A1111/Forge run_pip raises RuntimeError on a non-zero pip exit; it does
            # not return an exit code, so the except branch is the failure path.
            launch.run_pip(f'install -r "{path}"', desc)
        except Exception as e:
            print(f"[RanbooruX] ERROR: Failed to install {desc}: {e}", file=sys.stderr)


_install_req(os.path.join(ext_root, "requirements.txt"), "RanbooruX requirements")
