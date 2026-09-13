"""Constants for the Moonboon integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "moonboon"

#: The motor advertises no service UUIDs at all -- only its name -- so name is
#: the only thing we can match on.
LOCAL_NAME: Final = "Moonboon"

CONF_SPEED: Final = "speed"
CONF_MINUTES: Final = "minutes"
CONF_PROGRAM: Final = "program"
CONF_KEEP_CONNECTED: Final = "keep_connected"

PROGRAM_CONSTANT: Final = "constant"
PROGRAM_FADE: Final = "fade_out"
PROGRAMS: Final = [PROGRAM_CONSTANT, PROGRAM_FADE]

DEFAULT_SPEED: Final = 40
DEFAULT_MINUTES: Final = 60
DEFAULT_PROGRAM: Final = PROGRAM_FADE
DEFAULT_KEEP_CONNECTED: Final = True

#: Poll cadence. The motor pushes only on physical interaction -- it says
#: nothing when a program ends -- so the countdown has to be polled.
UPDATE_INTERVAL_RUNNING: Final = 20
#: The motor says nothing when someone starts it at the cradle, so being idle
#: still has to be polled at a rate that feels responsive.
UPDATE_INTERVAL_IDLE: Final = 60

#: Seconds to wait after the last slider movement before restarting the
#: program. Changing speed requires a full reload, so each step must not fire.
#: Swapping the program while running is cheap, so this can be short.
SETTINGS_DEBOUNCE: Final = 1.2

#: Ignore setting pushes this soon after our own write, so the echo of a
#: change we made is not mistaken for someone changing it at the cradle.
ECHO_SUPPRESSION: Final = 4.0

#: Upper bound on reconnect backoff, in seconds.
RECONNECT_BACKOFF_MAX: Final = 60
