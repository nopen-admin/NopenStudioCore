"""Product modes and disabled capabilities shared by the CLI."""

OPERATOR = "operator"
COMPANION = "companion"
MODE_NAMES = (OPERATOR, COMPANION)

# These are availability flags, independent of W001's acknowledgement records.
_RESTRICTED_CAPABILITIES = (
    "screen-read",
    "input-control",
    "microphone",
    "audio-output",
    "network",
)


def describe():
    return {
        "active_mode": OPERATOR,
        "modes": {
            OPERATOR: {"name": "Operator Buddy", "status": "AVAILABLE"},
            COMPANION: {"name": "Companion Buddy", "status": "NOT IMPLEMENTED"},
        },
        "capabilities": {
            name: {"status": "NOT IMPLEMENTED", "os_access": False}
            for name in _RESTRICTED_CAPABILITIES
        },
    }
