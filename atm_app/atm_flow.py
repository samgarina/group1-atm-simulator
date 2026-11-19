"""The ATM screen flow. Plain Python, no Django.

ATMFlow remembers where the user is (which screen, which card, PIN done or
not, a pending transaction). Django views pass user input to ATMFlow.
ATMFlow changes the account only through ATMService, so all money rules
stay in the account classes.

The flow state is a small plain dict (to_dict) that is saved in the session.
A PIN is never saved in it.
"""

from .atm_classes import _to_money, format_money
from .exceptions import ATMError, CardBlockedError

WELCOME_MESSAGE = "Welcome to BBko.\nPlease insert your ATM Bai card."
PIN_MESSAGE = "Please enter your six-digit PIN."
MENU_MESSAGE = "Please select a service."
AMOUNT_MESSAGE = "Please enter the amount."
EJECT_MESSAGE = "Please take your card."
THANK_YOU_MESSAGE = "Thank you for using BBko.\nPlease insert your Bai card."
OUT_OF_STEP_MESSAGE = "Please follow the instructions on the screen."
INVALID_SELECTION_MESSAGE = "Invalid selection."

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

    @property
    def screen_name(self):
        return self._state["screen"]

    @property
    def card_inserted(self):
        return bool(self._state["card"])

    @property
    def authenticated(self):
        return self._state["authed"]

    @property
    def card_number(self):
        """The number of the card in the machine. Empty text if there is none."""
        return self._state["card"]

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

    # ------------------------------------------------------------------
    # small helpers
    # ------------------------------------------------------------------

    def _account(self):
        card = self._service.get_card(self._state["card"])
        return self._service.get_account(card.account_number)

    def _go(self, screen, message, keep_pending=False):
        """Move to another screen and set its message."""
        if screen != "receipt_view":
            self._state["view_index"] = None
        if not keep_pending:
            self._state["pending"] = None
        self._state["screen"] = screen
        self._state["message"] = message

    def _end_session(self, message):
        """Remove the card and go back to the welcome screen."""
        self._state = self._fresh_state()
        self._state["message"] = message

    def _out_of_step(self):
        """Input that does not fit the current screen is ignored."""
        self._state["message"] = OUT_OF_STEP_MESSAGE

    @staticmethod
    def _limit_text(account):
        limit = getattr(account, "MAX_WITHDRAWAL", None)
        return "No limit" if limit is None else format_money(limit)

    # ------------------------------------------------------------------
    # what the monitor shows
    # ------------------------------------------------------------------

    def screen(self):
        builder = getattr(self, "_screen_" + self._state["screen"])
        return builder()

    def receipt_paper(self):
        """The newest receipt, if a slip waits in the printer. Else None."""
        if not self._state["receipt_ready"]:
            return None
        return self._service.recent_receipts(self._account().account_number, 1)[0]

    def cash_amount(self):
        """Cash waiting in the dispenser as a Decimal. None if there is none."""
        cash = self._state["cash"]
        return None if cash is None else _to_money(cash)

    def _screen_welcome(self):
        return Screen("welcome", "WELCOME", self._state["message"])

    def _screen_pin(self):
        return Screen("pin", "ENTER PIN", self._state["message"], input_mode="pin")

    def _screen_menu(self):
        options = {
            "L1": Option("Balance Inquiry", "balance"),
            "L2": Option("Cash Withdrawal", "withdraw_start"),
            "R1": Option("Change PIN", "change_pin_start"),
            "R2": Option("Additional Services", "additional"),
            "R4": Option("Exit", "exit"),
        }
        return Screen("menu", "ATM SERVICES", self._state["message"], options)

    def _screen_balance(self):
        account = self._account()
        rows = [
            ("Current Balance", format_money(account.balance)),
            ("Available Balance", format_money(account.available_balance)),
            ("Maximum Withdrawal", self._limit_text(account)),
        ]
        options = {
            "L4": Option("Yes", "withdraw_start"),
            "R4": Option("No", "menu"),
        }
        return Screen("balance", "BALANCE INQUIRY", self._state["message"],
                      options, rows=rows)

    def _screen_withdraw_amount(self):
        account = self._account()
        # No balance here: the balance is shown by Balance Inquiry and on the receipt.
        rows = [
            ("Maximum Withdrawal", self._limit_text(account)),
            ("Minimum Withdrawal", format_money(account.MIN_WITHDRAWAL)),
            ("In multiples of", f"PHP {account.BILL_STEP}"),
        ]
        return Screen("withdraw_amount", "CASH WITHDRAWAL", self._state["message"],
                      {"R4": Option("Back", "menu")}, input_mode="amount", rows=rows)

    def _screen_deposit_amount(self):
        account = self._account()
        rows = [
            ("Minimum Deposit", format_money(account.MIN_DEPOSIT)),
            ("In multiples of", f"PHP {account.BILL_STEP}"),
        ]
        return Screen("deposit_amount", "CASH DEPOSIT", self._state["message"],
                      {"R4": Option("Back", "additional")}, input_mode="amount", rows=rows)

    def _screen_confirm(self):
        options = {
            "L4": Option("Yes", "confirm_yes"),
            "R4": Option("No", "confirm_no"),
        }
        return Screen("confirm", "CONFIRM", self._state["message"], options)

    def _screen_collect(self):
        """The card (and the receipt and cash) wait in the machine. No buttons."""
        title = "TRANSACTION COMPLETE" if self._state["receipt_ready"] else "THANK YOU"
        return Screen("collect", title, self._state["message"])

    def _screen_additional(self):
        options = {
            "L1": Option("Cash Deposit", "deposit_start"),
            "L2": Option("Bank Statement", "mini_statement"),
            "L3": Option("Account Information", "account_info"),
            "R4": Option("Back", "menu"),
        }
        return Screen("additional", "ADDITIONAL SERVICES", self._state["message"], options)

    def _screen_mini_statement(self):
        receipts = self._service.recent_receipts(self._account().account_number)
        options = {}
        for i, receipt in enumerate(receipts):
            options[f"L{i + 1}"] = Option(
                f"{receipt.transaction_type} {receipt.amount:,.2f}",
                f"view_receipt:{i}",
                sub=f"{receipt.timestamp:%d %b %Y %I:%M %p}",
            )
        options["R4"] = Option("Back", "additional")
        message = (
            "Select a transaction to view its receipt." if receipts
            else "No transactions yet."
        )
        return Screen("mini_statement", "MINI STATEMENT", message, options)

    def _screen_receipt_view(self):
        account = self._account()
        receipt = self._service.recent_receipts(account.account_number)[self._state["view_index"]]
        return Screen("receipt_view", "RECEIPT", self._state["message"],
                      {"R4": Option("Back", "mini_statement")}, rows=receipt.rows())

    def _screen_account_info(self):
        account = self._account()
        rows = [
            ("Account Holder", account.holder_name),
            ("Account Type", account.account_type),
            ("Account No.", account.masked_number),
            ("Current Balance", format_money(account.balance)),
            ("Available Balance", format_money(account.available_balance)),
            ("Minimum Balance", format_money(account.MINIMUM_BALANCE)),
            ("Minimum Withdrawal", format_money(account.MIN_WITHDRAWAL)),
            ("Maximum Withdrawal", self._limit_text(account)),
            ("Minimum Deposit", format_money(account.MIN_DEPOSIT)),
        ]
        return Screen("account_info", "ACCOUNT INFORMATION", self._state["message"],
                      {"R4": Option("Back", "additional")}, rows=rows)

    def _screen_change_pin(self):
        return Screen("change_pin", "CHANGE PIN", self._state["message"],
                      {"R4": Option("Back", "menu")}, input_mode="change_pin",
                      prompts=list(CHANGE_PIN_PROMPTS))

    # ------------------------------------------------------------------
    # user input. The view calls these. Then it saves service and flow.
    # ------------------------------------------------------------------

    def insert_card(self, card_number):
        if self._state["screen"] != "welcome":
            return self._out_of_step()
        try:
            card = self._service.get_card(card_number)
        except ATMError as error:
            self._state["message"] = error.message
            return
        if card.is_blocked:
            self._state["message"] = "This card is blocked.\nPlease contact your bank."
            return
        self._state["card"] = card.card_number
        self._go("pin", PIN_MESSAGE)

    def submit_pin(self, pin):
        if self._state["screen"] != "pin":
            return self._out_of_step()
        try:
            self._service.verify_pin(self._state["card"], pin)
        except CardBlockedError as error:
            self._end_session(error.message + "\nPlease contact your bank.")
        except ATMError as error:
            self._state["message"] = error.message
        else:
            self._state["authed"] = True
            self._go("menu", MENU_MESSAGE)

    def submit_change_pin(self, current_pin, new_pin, confirm_pin):
        if self._state["screen"] != "change_pin":
            return self._out_of_step()
        try:
            self._service.change_pin(
                self._state["card"], current_pin, new_pin, confirm_pin
            )
        except CardBlockedError as error:
            self._end_session(error.message + "\nPlease contact your bank.")
        except ATMError as error:
            self._state["message"] = error.message
        else:
            self._go("menu", "PIN changed successfully.")

    def choose(self, slot):
        """A side button was pressed. slot is 'L1'...'L4' or 'R1'...'R4'."""
        option = self.screen().options.get(slot)
        if option is None:
            self._state["message"] = INVALID_SELECTION_MESSAGE
            return
        self._do(option.action)

    def submit_amount(self, value):
        """An amount was entered. The account checks it. Nothing is changed yet."""
        screen = self._state["screen"]
        if screen not in ("withdraw_amount", "deposit_amount"):
            return self._out_of_step()
        account = self._account()
        try:
            if screen == "withdraw_amount":
                kind, verb = "withdrawal", "Withdraw"
                amount = account.check_withdrawal(value)
            else:
                kind, verb = "deposit", "Deposit"
                amount = account.check_deposit(value)
        except ATMError as error:
            self._state["message"] = error.message
            return
        self._state["pending"] = {"kind": kind, "amount": str(amount)}
        self._go("confirm", f"{verb} {format_money(amount)}?", keep_pending=True)

    def cancel(self):
        """The Cancel key. Safe on every screen. It never changes a balance."""
        target = CANCEL_GOES_TO.get(self._state["screen"])
        if target is None:
            return  # welcome screen: nothing to cancel
        if target == "eject":
            self.eject()
        elif self._state["screen"] == "confirm":
            self._do("confirm_no")
        else:
            self._do(target)

    def eject(self):
        """Finish the session. The card comes out and waits to be taken."""
        if self._state["screen"] in ("welcome", "collect"):
            return
        self._state["receipt_ready"] = False
        self._state["cash"] = None
        self._go("collect", EJECT_MESSAGE)

    def finish(self):
        """The card, receipt and cash were taken. Back to the welcome screen."""
        if self._state["screen"] != "collect":
            return self._out_of_step()
        self._end_session(THANK_YOU_MESSAGE)

    # ------------------------------------------------------------------
    # actions behind the side buttons
    # ------------------------------------------------------------------

    def _do(self, action):
        if action == "menu":
            self._go("menu", MENU_MESSAGE)
        elif action == "balance":
            self._go("balance", "Would you like to proceed\nwith a withdrawal?")
        elif action == "withdraw_start":
            self._go("withdraw_amount", AMOUNT_MESSAGE)
        elif action == "deposit_start":
            self._go("deposit_amount", AMOUNT_MESSAGE)
        elif action == "change_pin_start":
            self._go("change_pin", CHANGE_PIN_PROMPTS[0])
        elif action == "additional":
            self._go("additional", MENU_MESSAGE)
        elif action == "mini_statement":
            self._go("mini_statement", "")
        elif action == "account_info":
            self._go("account_info", "")
        elif action.startswith("view_receipt:"):
            self._state["view_index"] = int(action.split(":")[1])
            self._go("receipt_view", "")
            # _go clears view_index only for other screens, so it is kept here
        elif action == "confirm_yes":
            self._confirm()
        elif action == "confirm_no":
            self._go("menu", "Transaction cancelled.")
        elif action == "exit":
            self.eject()

    def _confirm(self):
        """Run the pending transaction. It can run only once."""
        pending = self._state["pending"]
        if pending is None:
            return self._out_of_step()
        account = self._account()
        # Clear first. A second request finds nothing to confirm.
        self._state["pending"] = None
        try:
            if pending["kind"] == "withdrawal":
                transaction = self._service.withdraw(account.account_number, pending["amount"])
            else:
                transaction = self._service.deposit(account.account_number, pending["amount"])
        except ATMError as error:
            back = "withdraw_amount" if pending["kind"] == "withdrawal" else "deposit_amount"
            self._go(back, "Transaction declined.\n" + error.message)
            return

        # Withdrawal and deposit end the session: card, receipt (and cash) come out.
        self._state["receipt_ready"] = True
        if pending["kind"] == "withdrawal":
            self._state["cash"] = str(transaction.amount)
            message = "Transaction approved.\nPlease take your card, cash and receipt."
        else:
            message = "Transaction approved.\nPlease take your card and receipt."
        self._go("collect", message)