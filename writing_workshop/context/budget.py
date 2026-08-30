# SPDX-License-Identifier: Apache-2.0
"""The budget: what the loaded model can hold, and what holding it costs.

ATK measured the gap this module exists for. Across one model folder the
DECLARED context and the usable one differ by 10x to 100x — Qwythos-9B has
"1M" in its filename and fits 75,448 tokens on a 16 GB card — and every
number here comes from the host's measurement rather than from a header.

The second line of the meter is the one people forget. Since layer offload
became a choice rather than a failure, context is a PURCHASE: the operator
raises it, twenty-eight of forty layers stay on the card, six gigabytes
move into system RAM, and drafting gets slower for a reason nothing on
screen connects to the thing they just did. Naming the price is cheap and
it is the difference between a tool that feels considered and one that
feels flaky.
"""

from __future__ import annotations

from ..ports import ModelInfo
from ..types import Budget

#: Left for the model to WRITE IN. A budget that packs the window to its
#: last token leaves nowhere for the answer, and llama.cpp's response to
#: that is to truncate the prompt, not to refuse.
DEFAULT_RESERVE = 1024


def from_model(info: ModelInfo | None,
               reserve: int = DEFAULT_RESERVE) -> Budget:
    if info is None or not info.name:
        return Budget(reserve_output=reserve)
    return Budget(
        model=info.name, usable_tokens=info.usable_tokens or 0,
        declared_tokens=info.declared_tokens or 0,
        layers_on_card=info.layers_on_card, total_layers=info.total_layers,
        host_mb=info.host_mb, reserve_output=reserve,
        alternative=info.alternative, measured=info.measured)


def offline(reserve: int = DEFAULT_RESERVE) -> Budget:
    """No model. Named rather than improvised, because "no model" is a
    supported state here and not an error."""
    return Budget(reserve_output=reserve)
