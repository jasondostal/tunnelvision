"""Port event hooks — fire user-configured scripts when port assignments change.

Used by both PIA (PortForwardService) and Proton (NatPMPService).
Non-blocking, failure-tolerant: hook errors are logged but never propagate.
"""

import asyncio
import logging
import shlex

from api.constants import SUBPROCESS_TIMEOUT_VPN

logger = logging.getLogger(__name__)


async def fire_port_change_hook(hook_script: str, port: int) -> None:
    """Run the configured hook script with the assigned port as the sole argument.

    port=0 signals that port forwarding has been released.
    Executes asynchronously and does not block the caller.
    """
    if not hook_script:
        return

    try:
        parts = shlex.split(hook_script)
        proc = await asyncio.create_subprocess_exec(
            *parts, str(port),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=SUBPROCESS_TIMEOUT_VPN
        )
        if proc.returncode != 0:
            logger.warning(
                f"Port hook exited {proc.returncode}: {stderr.decode().strip()}"
            )
        else:
            logger.info(f"Port hook fired: port={port}")
    except asyncio.TimeoutError:
        logger.warning(f"Port hook timed out ({SUBPROCESS_TIMEOUT_VPN}s)")
    except Exception as e:
        logger.warning(f"Port hook error: {e}")
