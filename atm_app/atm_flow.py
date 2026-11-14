
from .atm_classes import _to_money, format_money
from .exceptions import ATMError, CardBlockedError

WELCOME_MESSAGE = "Welcome to PELEC Bank.\nPlease insert your ATM card."



# The three prompts of Change PIN. JavaScript shows them one by one and keeps
# the typed PINs in memory. All three are sent together. Nothing is saved.
CHANGE_PIN_PROMPTS = (
    "Enter your current PIN.",
    "Enter your new six-digit PIN.",
    "Confirm your new PIN.",
)

SCREEN_NAMES = (
    "welcome", "pin", "menu", "balance", "withdraw_amount", "deposit_amount",
    "confirm", "collect", "additional", "mini_statement", "receipt_view",
    "account_info", "change_pin",
)

# Where Cancel goes from each screen. "eject" ends the session.
CANCEL_GOES_TO = {
    "pin": "eject",
    "menu": "eject",
    "balance": "menu",
    "withdraw_amount": "menu",
    "deposit_amount": "additional",
    "confirm": "menu",
    "additional": "menu",
    "mini_statement": "additional",
    "receipt_view": "mini_statement",
    "account_info": "additional",
    "change_pin": "menu",
}


class Option:
    """One choice on the monitor, next to one physical side button."""

    def __init__(self, label, action, sub=""):
        self.label = label
        self.action = action
        self.sub = sub  # small second line, may be empty


class Screen:
    """What the monitor shows. Plain data. The template draws it."""

    LEFT_SLOTS = ("L1", "L2", "L3", "L4")
    RIGHT_SLOTS = ("R1", "R2", "R3", "R4")

    def __init__(self, name, title, message, options=None, input_mode="none",
                 prompts=None, rows=None):
        self.name = name
        self.title = title
        self.message = message
        self.options = options or {}      # slot name -> Option
        self.input_mode = input_mode      # "none", "pin", "amount", "change_pin"
        self.prompts = prompts or []      # used by change_pin
        self.rows = rows or []            # (label, value) pairs to show

    def left_options(self):
        """Always 4 items. None means the button stays visible but disabled."""
        return [self.options.get(slot) for slot in self.LEFT_SLOTS]

    def right_options(self):
        return [self.options.get(slot) for slot in self.RIGHT_SLOTS]











class ATMFlow:
    """Runs the ATM screens for one browser session."""

    def __init__(self, service, state=None):
        self._service = service
        self._state = state or self._fresh_state()

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------

    @staticmethod
    def _fresh_state():
        return {
            "screen": "welcome",
            "card": "",
            "authed": False,
            "pending": None,        # {"kind": ..., "amount": ...} on the confirm screen
            "view_index": None,     # which mini-statement receipt is open
            "message": WELCOME_MESSAGE,
            "receipt_ready": False,  # a slip waits in the printer
            "cash": None,            # cash waiting in the dispenser (text)
        }

















    def to_dict(self):
        state = dict(self._state)
        if state["pending"] is not None:
            state["pending"] = dict(state["pending"])
        return state

    @classmethod
    def from_dict(cls, service, data):
        """Rebuild from saved data. Raise ATMError if the data is not valid."""
        keys = ("screen", "card", "authed", "pending", "view_index",
                "message", "receipt_ready", "cash")
        try:
            state = {key: data[key] for key in keys}
        except (KeyError, TypeError):
            raise ATMError("Invalid saved flow data.")
        flow = cls(service, state)
        flow._check_state()
        return flow

    def _check_state(self):
        st = self._state
        bad = ATMError("Invalid saved flow data.")
        try:
            if st["screen"] not in SCREEN_NAMES:
                raise bad
            if not isinstance(st["message"], str) or len(st["message"]) > 300:
                raise bad
            if not isinstance(st["authed"], bool) or not isinstance(st["receipt_ready"], bool):
                raise bad
            if not isinstance(st["card"], str):
                raise bad

            # Card and PIN state must match the screen.
            if st["screen"] == "welcome":
                if st["card"] or st["authed"]:
                    raise bad
            else:
                card = self._service.get_card(st["card"])  # raises if unknown
                if card.is_blocked:
                    raise bad
                if st["screen"] == "pin" and st["authed"]:
                    raise bad  # the PIN screen is before the PIN is accepted
                if st["screen"] not in ("pin", "collect") and not st["authed"]:
                    raise bad  # every other screen is after the PIN

            # A slip waits only after a transaction, on the collect screen.
            if st["receipt_ready"] and (st["screen"] != "collect" or not st["authed"]):
                raise bad

            # Pending transaction only exists on the confirm screen.
            pending = st["pending"]
            if (pending is not None) != (st["screen"] == "confirm"):
                raise bad
            if pending is not None:
                if pending["kind"] not in ("withdrawal", "deposit"):
                    raise bad
                if _to_money(pending["amount"]) <= 0:
                    raise bad

            # Cash waits only after a withdrawal, on the collect screen.
            if st["cash"] is not None:
                if st["screen"] != "collect" or not st["receipt_ready"]:
                    raise bad
                if _to_money(st["cash"]) <= 0:
                    raise bad

            # Open receipt must exist.
            if st["screen"] == "receipt_view":
                index = st["view_index"]
                if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                    raise bad
                receipts = self._service.recent_receipts(self._account().account_number)
                if index >= len(receipts):
                    raise bad
            elif st["view_index"] is not None:
                raise bad
        except ATMError:
            raise
        except (KeyError, TypeError, ValueError):
            raise bad
