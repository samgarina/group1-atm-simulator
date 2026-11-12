import hashlib
import hmac
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .exceptions import (
    ATMError,
    InvalidAmountError,
    InsufficientFundsError,
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
    
class Account:
    """A bank account. Parent class of SavingsAccount and CheckingAccount."""
    account_type = "Account"
    MINIMUM_BALANCE = Decimal("0.00")   # must remain in the account after a withdrawal
    MIN_WITHDRAWAL = Decimal("100.00")  # smallest amount allowed in one withdrawal
    MIN_DEPOSIT = Decimal("100.00")     # smallest amount allowed in one deposit
    BILL_STEP = Decimal("100")          # cash is withdrawn or deposited in multiples of this
    MAX_SAVED_TRANSACTIONS = 10

    # Constructor with account_number, owner (holder_name), and starting balance
    def __init__(self, account_number, holder_name, balance="0", transactions=None):
        if not holder_name or not str(holder_name).strip():
            raise ATMError("Account holder name is required.")
        
        balance = _to_money(balance)
        if balance < 0:
            raise InvalidAmountError("Opening balance cannot be negative.")
        
        self._account_number = str(account_number)
        self._holder_name = str(holder_name).strip()
        
        # Private _balance
        self._balance = balance
        self._transactions = list(transactions) if transactions else []

    # Read-only balance property
    @property
    def balance(self):
        return self._balance

    @property
    def account_number(self):
        return self._account_number

    @property
    def holder_name(self):
        return self._holder_name