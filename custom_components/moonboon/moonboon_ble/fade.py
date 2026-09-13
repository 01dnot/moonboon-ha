"""The fade-out ramp used by the official Moonboon app.

The motor has no fade feature. The app computes the ramp itself and uploads it
as a multi-step program. The formula was derived from captured app traffic:

    speed_k = floor(S * k / N)   for k = N..1

Verified against five captured sequences (N=6 and N=12), exact match --
including values such as 20, 18, 16, 15, 13, 11 = floor(20 * k / 12).
"""

from __future__ import annotations

from .models import Step

#: Number of steps the app uses for its standard fade.
DEFAULT_STEPS = 6
#: Minutes spent on each step of the ramp-down.
DEFAULT_TAIL_MINUTES = 1


def constant(speed: int, minutes: int) -> list[Step]:
    """A single step: one speed held for the whole duration."""
    return [Step(speed=speed, timer=minutes)]


def fade_out(
    speed: int,
    minutes: int,
    steps: int = DEFAULT_STEPS,
    tail: int = DEFAULT_TAIL_MINUTES,
) -> list[Step]:
    """Build the app's fade-out program.

    The head step holds the chosen speed for whatever time is left after the
    ramp; each subsequent step drops the speed linearly toward zero.
    """
    head = max(1, minutes - tail * (steps - 1))
    return [
        Step(speed=(speed * k) // steps, timer=head if index == 0 else tail)
        for index, k in enumerate(range(steps, 0, -1))
    ]
