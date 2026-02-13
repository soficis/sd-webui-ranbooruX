from __future__ import annotations

import logging
from typing import Tuple

logger = logging.getLogger("ranboorux")


def verify_patch_target(
    target: object, method_name: str, *, require_callable: bool = True
) -> Tuple[bool, str]:
    if target is None:
        message = f"ADetailer patch target missing: {method_name}"
        logger.warning(message)
        return False, message
    if not hasattr(target, method_name):
        message = f"ADetailer patch target has no '{method_name}'"
        logger.warning(message)
        return False, message
    if require_callable and not callable(getattr(target, method_name, None)):
        message = f"ADetailer patch target '{method_name}' is not callable"
        logger.warning(message)
        return False, message
    message = f"ADetailer patch target verified: {target.__class__.__name__}.{method_name}"
    logger.info(message)
    return True, message
