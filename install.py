import os
import sys

import launch

ext_root = os.path.dirname(__file__)


def _install_req(path, desc):
    if os.path.exists(path):
        try:
            result = launch.run_pip(f'install -r "{path}"', desc)
            if isinstance(result, int) and result != 0:
                print(
                    f"[RanbooruX] ERROR: Pip installation of {desc} failed with exit code {result}",
                    file=sys.stderr,
                )
            elif isinstance(result, tuple) and len(result) > 0 and result[0] != 0:
                print(
                    f"[RanbooruX] ERROR: Pip installation of {desc} failed with exit code {result[0]}",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"[RanbooruX] ERROR: Failed to install {desc}: {e}", file=sys.stderr)


_install_req(os.path.join(ext_root, "requirements.txt"), "RanbooruX requirements")
