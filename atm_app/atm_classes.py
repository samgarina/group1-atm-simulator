import hashlib
import hmac
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from .exceptions import (
    ATMError,
    InsufficientFundsError,
    InvalidAmountError,
    MinimumDepositError,
    MinimumWithdrawalError,
    WithdrawalLimitError,
)

# added by senilong

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