import hashlib
import hmac
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation


from .exceptions import (
    ATMError,
    CardBlockedError,
    IncorrectPinError,
    InsufficientFundsError,
    InvalidAmountError,
    InvalidPinError,
    MinimumDepositError,
    MinimumWithdrawalError,
    MinimumWithdrawalError,
    WithdrawalLimitError,
)

def _to_money(value):
    """Turn a value into a Decimal with exactly 2 decimal places.

    Raises InvalidAmountError if the value is not a valid money number.
    """
    try:
        # str() first: Decimal(0.1) from a float gives a wrong long number.
        money = Decimal(str(value))
    except InvalidOperation:
        raise InvalidAmountError()

    # Decimal("NaN") and Decimal("Infinity") are valid Decimals. Reject them.
    if not money.is_finite():
        raise InvalidAmountError()

    # Money has at most 2 decimal places (centavos).
    if money.as_tuple().exponent < -2:
        raise InvalidAmountError("Amount cannot have more than 2 decimal places.")

    try:
        return money.quantize(Decimal("0.01"))
    except InvalidOperation:
        # Number has too many digits for Decimal to hold.
        raise InvalidAmountError("Amount is too large.")

def format_money(value):
    """Return money as text for the screen, for example 'PHP 5,000.00'."""
    return f"PHP {value:,.2f}"

class Transaction:
    """One successful ATM operation (a deposit or a withdrawal)."""

    VALID_KINDS = ("deposit", "withdrawal")

    def __init__(self, kind, amount, balance_after, timestamp=None):
        if kind not in self.VALID_KINDS:
            raise ATMError("Unknown transaction type.")

        amount = _to_money(amount)
        balance_after = _to_money(balance_after)

        if amount <= 0:
            raise InvalidAmountError("Amount must be greater than zero.")
        if balance_after < 0:
            raise InvalidAmountError("Balance cannot be negative.")

        self._kind = kind
        self._amount = amount
        self._balance_after = balance_after
        # No microseconds, so the timestamp survives a to_dict/from_dict round trip.
        self._timestamp = timestamp or datetime.now().replace(microsecond=0)

    # Read-only properties: outside code can read, but not change.
    @property
    def kind(self):
        return self._kind

    @property
    def amount(self):
        return self._amount

    @property
    def balance_after(self):
        return self._balance_after

    @property
    def timestamp(self):
        return self._timestamp

    def to_dict(self):
        """Convert to a plain dict that can be saved in a Django session."""
        return {
            "kind": self._kind,
            "amount": str(self._amount),
            "balance_after": str(self._balance_after),
            "timestamp": self._timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data):
        """Rebuild a Transaction from a dict made by to_dict()."""
        return cls(
            kind=data["kind"],
            amount=data["amount"],
            balance_after=data["balance_after"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )

    def __str__(self):
        return (
            f"{self._timestamp:%Y-%m-%d %H:%M:%S} | {self._kind} | "
            f"PHP {self._amount} | balance PHP {self._balance_after}"
        )


class Account:
    """A bank account. Parent class of SavingsAccount and CheckingAccount."""

    account_type = "Account"

    MINIMUM_BALANCE = Decimal("0.00")   # must remain in the account after a withdrawal
    MIN_WITHDRAWAL = Decimal("100.00")  # smallest amount allowed in one withdrawal
    MIN_DEPOSIT = Decimal("100.00")     # smallest amount allowed in one deposit
    BILL_STEP = Decimal("100")          # cash is withdrawn or deposited in multiples of this

    # Only the newest transactions are saved in the session cookie.
    MAX_SAVED_TRANSACTIONS = 10

    def __init__(self, account_number, holder_name, balance="0", transactions=None):
        if not holder_name or not str(holder_name).strip():
            raise ATMError("Account holder name is required.")

        balance = _to_money(balance)
        if balance < 0:
            raise InvalidAmountError("Opening balance cannot be negative.")

        self._account_number = str(account_number)
        self._holder_name = str(holder_name).strip()
        self._balance = balance
        self._transactions = list(transactions) if transactions else []

    # Read-only properties.
    @property
    def account_number(self):
        return self._account_number

    @property
    def holder_name(self):
        return self._holder_name

    @property
    def masked_number(self):
        """Account number with only the last 4 digits shown."""
        return "****" + self._account_number[-4:]

    @property
    def balance(self):
        return self._balance

    @property
    def transactions(self):
        # Return a copy so outside code cannot edit the real history.
        return list(self._transactions)

    def available_for(self, balance):
        """Money that can be taken out when the balance is this amount.

        It is the balance minus the minimum balance, and never below zero.
        """
        return max(balance - self.MINIMUM_BALANCE, Decimal("0.00"))

    @property
    def available_balance(self):
        return self.available_for(self._balance)

    def _validate_amount(self, amount):
        """Return amount as clean Decimal. Raise if zero or negative."""
        amount = _to_money(amount)
        if amount <= 0:
            raise InvalidAmountError("Amount must be greater than zero.")
        return amount

    def _check_bill_step(self, amount):
        """Cash comes in whole bills: the amount must be a multiple of BILL_STEP."""
        if amount % self.BILL_STEP != 0:
            raise InvalidAmountError(
                f"Amount must be in multiples of PHP {self.BILL_STEP}."
            )

    def check_deposit(self, amount):
        """Check a deposit. Return the clean amount. Change nothing."""
        amount = self._validate_amount(amount)
        if amount < self.MIN_DEPOSIT:
            raise MinimumDepositError(f"Minimum deposit is PHP {self.MIN_DEPOSIT}.")
        self._check_bill_step(amount)
        return amount

    def deposit(self, amount):
        amount = self.check_deposit(amount)
        new_balance = self._balance + amount

        # Build the record first. If anything fails, the balance is untouched.
        transaction = Transaction("deposit", amount, new_balance)

        self._balance = new_balance
        self._transactions.append(transaction)
        return transaction

    def check_withdrawal(self, amount):
        """Check a withdrawal. Return the clean amount. Change nothing.

        Raises an ATMError if the withdrawal is not allowed.
        Child classes override this to add their own rules.
        """
        amount = self._validate_amount(amount)
        if amount < self.MIN_WITHDRAWAL:
            raise MinimumWithdrawalError(
                f"Minimum withdrawal is PHP {self.MIN_WITHDRAWAL}."
            )
        self._check_bill_step(amount)
        if amount > self._balance:
            raise InsufficientFundsError()
        return amount

    def withdraw(self, amount):
        # The rules live in check_withdrawal(). Each account type has its own.
        amount = self.check_withdrawal(amount)
        new_balance = self._balance - amount

        transaction = Transaction("withdrawal", amount, new_balance)

        self._balance = new_balance
        self._transactions.append(transaction)
        return transaction

    def to_dict(self):
        """Convert to a plain dict for the Django session."""
        return {
            "account_type": self.account_type,
            "account_number": self._account_number,
            "holder_name": self._holder_name,
            "balance": str(self._balance),
            "transactions": [
                t.to_dict() for t in self._transactions[-self.MAX_SAVED_TRANSACTIONS:]
            ],
        }

    @classmethod
    def from_dict(cls, data):
        """Rebuild an account from a dict made by to_dict()."""
        return cls(
            account_number=data["account_number"],
            holder_name=data["holder_name"],
            balance=data["balance"],
            transactions=[Transaction.from_dict(t) for t in data["transactions"]],
        )

    def __str__(self):
        return f"{self.account_type} {self._account_number} ({self._holder_name}): PHP {self._balance}"


class SavingsAccount(Account):
    """A savings account. It keeps a minimum balance and a lower withdrawal limit."""

    account_type = "Savings Account"
    MINIMUM_BALANCE = Decimal("500.00")
    MAX_WITHDRAWAL = Decimal("5000.00")

    def __init__(self, account_number, holder_name, balance="0", transactions=None):
        # Let the parent do its normal setup and checks first.
        super().__init__(account_number, holder_name, balance, transactions)

        # Then add the savings rule.
        if self._balance < self.MINIMUM_BALANCE:
            raise InvalidAmountError(
                f"Opening balance must be at least PHP {self.MINIMUM_BALANCE}."
            )

    def check_withdrawal(self, amount):
        # Common rules first (amount, minimum withdrawal, bills, balance).
        amount = super().check_withdrawal(amount)

        # Savings rule 1: the balance after withdrawal must stay at or above the minimum.
        if self._balance - amount < self.MINIMUM_BALANCE:
            raise InsufficientFundsError(
                f"Savings accounts must keep a minimum balance of PHP {self.MINIMUM_BALANCE}."
            )

        # Savings rule 2: one withdrawal cannot be above the savings limit.
        if amount > self.MAX_WITHDRAWAL:
            raise WithdrawalLimitError(
                f"Savings accounts allow a maximum of PHP {self.MAX_WITHDRAWAL} per withdrawal."
            )
        return amount


class CheckingAccount(Account):
    """A checking account. It has a higher withdrawal limit than savings."""

    account_type = "Checking Account"
    MAX_WITHDRAWAL = Decimal("20000.00")

    def check_withdrawal(self, amount):
        # Common rules first (amount, minimum withdrawal, bills, balance).
        amount = super().check_withdrawal(amount)

        # Checking rule: one withdrawal cannot be above the limit.
        if amount > self.MAX_WITHDRAWAL:
            raise WithdrawalLimitError(
                f"Checking accounts allow a maximum of PHP {self.MAX_WITHDRAWAL} per withdrawal."
            )
        return amount

class Receipt:
    """An ATM slip for one transaction. Built from a Transaction and its account.

    Nothing is saved. A receipt can be rebuilt at any time, because the
    available balance only depends on the balance after the transaction
    and the account's fixed minimum balance.
    """

    BANK_NAME = "BBko"
    LOCATION = "CTU"
    TYPE_LABELS = {
        "withdrawal": "Cash Withdrawal",
        "deposit": "Cash Deposit",
    }

    def __init__(self, transaction, account):
        self._transaction = transaction
        self._account_type = account.account_type
        # Show only the last 4 digits, like a real slip.
        self._masked_account = account.masked_number
        self._available_balance = account.available_for(transaction.balance_after)

    # Read-only properties.
    @property
    def bank_name(self):
        return self.BANK_NAME

    @property
    def location(self):
        return self.LOCATION

    @property
    def timestamp(self):
        return self._transaction.timestamp

    @property
    def transaction_type(self):
        return self.TYPE_LABELS[self._transaction.kind]

    @property
    def amount(self):
        return self._transaction.amount

    @property
    def account_type(self):
        return self._account_type

    @property
    def masked_account(self):
        return self._masked_account

    @property
    def current_balance(self):
        """The real balance in the account after this transaction."""
        return self._transaction.balance_after

    @property
    def available_balance(self):
        """What can be withdrawn after this transaction (balance - minimum)."""
        return self._available_balance

    def rows(self):
        """Label and value pairs in slip order. The template prints them."""
        return [
            ("Date", f"{self.timestamp:%d %b %Y}"),
            ("Time", f"{self.timestamp:%I:%M:%S %p}"),
            ("Location", self.location),
            ("Transaction", self.transaction_type),
            ("Amount", format_money(self.amount)),
            ("Account", self.account_type),
            ("Account No.", self.masked_account),
            ("Current Balance", format_money(self.current_balance)),
            ("Available Balance", format_money(self.available_balance)),
        ]

class Card:
    """A bank card. It checks the PIN and counts wrong tries.

    The PIN is never stored. Only a salted hash is stored ("salt$hash").
    """

    PIN_LENGTH = 6
    MAX_ATTEMPTS = 3
    PIN_ITERATIONS = 100_000

    def __init__(self, card_number, account_number, pin_hash,
                 failed_attempts=0, blocked=False):
        card_number = str(card_number).strip()
        if not card_number:
            raise ATMError("Card number is required.")
        self._check_saved_hash(pin_hash)
        if (
            isinstance(failed_attempts, bool)
            or not isinstance(failed_attempts, int)
            or not 0 <= failed_attempts <= self.MAX_ATTEMPTS
        ):
            raise ATMError("Invalid saved card data.")
        if not isinstance(blocked, bool):
            raise ATMError("Invalid saved card data.")

        self._card_number = card_number
        self._account_number = str(account_number)
        self._pin_hash = pin_hash
        self._failed_attempts = failed_attempts
        self._blocked = blocked

    @classmethod
    def create(cls, card_number, account_number, pin):
        """Make a new card. The PIN is checked, hashed, then forgotten."""
        cls._check_pin_format(pin)
        return cls(card_number, account_number, cls._hash_pin(pin))

    # --- helpers -------------------------------------------------------

    @classmethod
    def _check_pin_format(cls, pin):
        # isascii(): isdigit() alone also accepts digits from other scripts.
        if not (
            isinstance(pin, str)
            and pin.isascii()
            and pin.isdigit()
            and len(pin) == cls.PIN_LENGTH
        ):
            raise InvalidPinError(f"PIN must be exactly {cls.PIN_LENGTH} digits.")

    @staticmethod
    def _check_saved_hash(pin_hash):
        """Saved hash must look like 'salt$hash' with hex text on both sides."""
        try:
            salt, digest = pin_hash.split("$")
            bytes.fromhex(salt)
            bytes.fromhex(digest)
        except (AttributeError, ValueError):
            raise ATMError("Invalid saved card data.")

    @classmethod
    def _hash_pin(cls, pin, salt=None):
        """Return 'salt$hash'. A new random salt is made if none is given."""
        salt = salt or os.urandom(8).hex()
        digest = hashlib.pbkdf2_hmac(
            "sha256", pin.encode(), bytes.fromhex(salt), cls.PIN_ITERATIONS
        )
        return f"{salt}${digest.hex()}"

    def _pin_matches(self, pin):
        salt, stored = self._pin_hash.split("$")
        candidate = self._hash_pin(pin, salt).split("$")[1]
        # compare_digest takes the same time for any input. It avoids timing leaks.
        return hmac.compare_digest(candidate, stored)

    # --- read-only properties -----------------------------------------

    @property
    def card_number(self):
        return self._card_number

    @property
    def account_number(self):
        return self._account_number

    @property
    def failed_attempts(self):
        return self._failed_attempts

    @property
    def attempts_left(self):
        return self.MAX_ATTEMPTS - self._failed_attempts

    @property
    def is_blocked(self):
        return self._blocked

    # --- actions -------------------------------------------------------

    def verify_pin(self, pin):
        """Return normally if the PIN is right. Raise an ATMError if not.

        A wrong PIN counts as a failed attempt. The last allowed wrong
        attempt blocks the card. A PIN with the wrong format is not counted.
        """
        if self._blocked:
            raise CardBlockedError()
        self._check_pin_format(pin)

        if self._pin_matches(pin):
            self._failed_attempts = 0
            return

        self._failed_attempts += 1
        if self._failed_attempts >= self.MAX_ATTEMPTS:
            self._blocked = True
            raise CardBlockedError()

        left = self.attempts_left
        if left == 1:
            message = "Incorrect PIN. Last attempt remaining."
        else:
            message = "Incorrect PIN. Please try again."
        raise IncorrectPinError(message, attempts_left=left)

    def change_pin(self, current_pin, new_pin, confirm_pin):
        """Replace the PIN. Nothing changes if any check fails."""
        # Format and match checks first, so a typing mistake costs no attempt.
        self._check_pin_format(new_pin)
        self._check_pin_format(confirm_pin)
        if new_pin != confirm_pin:
            raise InvalidPinError("PINs do not match.")

        self.verify_pin(current_pin)  # a wrong current PIN counts as an attempt

        if new_pin == current_pin:
            raise InvalidPinError("New PIN must be different.")
        self._pin_hash = self._hash_pin(new_pin)

    # --- session -------------------------------------------------------

    def to_dict(self):
        return {
            "card_number": self._card_number,
            "account_number": self._account_number,
            "pin_hash": self._pin_hash,
            "failed_attempts": self._failed_attempts,
            "blocked": self._blocked,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            card_number=data["card_number"],
            account_number=data["account_number"],
            pin_hash=data["pin_hash"],
            failed_attempts=data["failed_attempts"],
            blocked=data["blocked"],
        )

    def __str__(self):
        return f"Card {self._card_number} for account {self._account_number}"

class ATMService:
    """The ATM machine. Holds all accounts and runs operations on them.

    Django views talk to this class. This class talks to the accounts.
    """

    # Maps the saved account_type text back to the right class.
    ACCOUNT_CLASSES = {
        SavingsAccount.account_type: SavingsAccount,
        CheckingAccount.account_type: CheckingAccount,
    }

    # Demo cards: (card number, account number, starting PIN). Fictional data.
    SAMPLE_CARDS = (
        ("5000000000001001", "1001", "123456"),
        ("5000000000002001", "2001", "654321"),
    )

    def __init__(self, accounts=None, cards=None):
        self._accounts = {}  # account_number -> account object
        self._cards = {}     # card_number -> card object
        for account in accounts or []:
            self.add_account(account)
        # Cards come after accounts: each card must point to a real account.
        for card in cards or []:
            self.add_card(card)

    @classmethod
    def with_sample_accounts(cls):
        accounts = [
            SavingsAccount("1001", "Maria Santos", "15000"),
            CheckingAccount("2001", "Juan Dela Cruz", "25000"),
        ]
        cards = [
            Card.create(number, account_number, pin)
            for number, account_number, pin in cls.SAMPLE_CARDS
        ]
        return cls(accounts, cards)

    def add_account(self, account):
        if account.account_number in self._accounts:
            raise ATMError("Account number already exists.")
        self._accounts[account.account_number] = account

    def get_account(self, account_number):
        # str(): form input and saved data may give a number as text or int.
        account = self._accounts.get(str(account_number))
        if account is None:
            raise ATMError("Account not found.")
        return account

    def list_accounts(self):
        return list(self._accounts.values())

    def add_card(self, card):
        if card.card_number in self._cards:
            raise ATMError("Card number already exists.")
        self.get_account(card.account_number)  # raises if the account is missing
        self._cards[card.card_number] = card

    def get_card(self, card_number):
        card = self._cards.get(str(card_number))
        if card is None:
            raise ATMError("Card not found.")
        return card

    def list_cards(self):
        return list(self._cards.values())

    def make_receipt(self, account_number, transaction):
        """Build the receipt for a transaction of this account."""
        return Receipt(transaction, self.get_account(account_number))

    def recent_receipts(self, account_number, count=4):
        """Receipts of the newest transactions, newest first (mini statement)."""
        account = self.get_account(account_number)
        newest_first = list(reversed(account.transactions))
        return [Receipt(t, account) for t in newest_first[:count]]

    def verify_pin(self, card_number, pin):
        """Check the PIN. Return the account of the card if it is right."""
        card = self.get_card(card_number)
        card.verify_pin(pin)
        return self.get_account(card.account_number)

    def change_pin(self, card_number, current_pin, new_pin, confirm_pin):
        self.get_card(card_number).change_pin(current_pin, new_pin, confirm_pin)

    def get_balance(self, account_number):
        return self.get_account(account_number).balance

    def deposit(self, account_number, amount):
        return self.get_account(account_number).deposit(amount)

    def withdraw(self, account_number, amount):
        # The service does not know the account type. Each account applies its own rule.
        return self.get_account(account_number).withdraw(amount)

    def get_history(self, account_number):
        return self.get_account(account_number).transactions

    def to_dict(self):
        """Convert everything to a plain dict for the Django session."""
        return {
            "accounts": [a.to_dict() for a in self._accounts.values()],
            "cards": [c.to_dict() for c in self._cards.values()],
        }
    @classmethod
    def from_dict(cls, data):
        """Rebuild the service from a dict made by to_dict()."""
        accounts = []
        for account_data in data["accounts"]:
            account_class = cls.ACCOUNT_CLASSES.get(account_data["account_type"])
            if account_class is None:
                raise ATMError("Unknown account type in saved data.")
            accounts.append(account_class.from_dict(account_data))
        # Old saved data has no "cards" key. KeyError makes the session reset safely.
        cards = [Card.from_dict(card_data) for card_data in data["cards"]]
        return cls(accounts, cards)



