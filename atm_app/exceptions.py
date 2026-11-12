class ATMError(Exception):
    """Base class for all ATM errors in this project."""

    default_message = "An ATM error occurred."

    def __init__(self, message=None):
        self.message = message or self.default_message
        super().__init__(self.message)


class InvalidAmountError(ATMError):
    """Amount is zero, negative, or not a number."""

    default_message = "Invalid amount. Enter a number greater than zero."


class InsufficientFundsError(ATMError):
    """Account does not have enough money for the withdrawal."""

    default_message = "Insufficient funds for this withdrawal."


class WithdrawalLimitError(ATMError):
    """Withdrawal is above the account's allowed limit."""

    default_message = "Withdrawal exceeds the allowed limit."

class MinimumWithdrawalError(ATMError):
    """Withdrawal is below the account's minimum withdrawal."""

    default_message = "Amount is below the minimum withdrawal."

class InvalidPinError(ATMError):
    """PIN has the wrong format, or two typed PINs do not match."""

    default_message = "Invalid PIN. Enter exactly 6 digits."

class IncorrectPinError(ATMError):
    """The typed PIN is wrong. The card is not blocked yet."""

    default_message = "Incorrect PIN. Please try again."

    def __init__(self, message=None, attempts_left=None):
        self.attempts_left = attempts_left
        super().__init__(message)

class CardBlockedError(ATMError):
    """The card is blocked after too many wrong PIN attempts."""

    default_message = "Card blocked. Too many incorrect PIN attempts."

class MinimumDepositError(ATMError):
    """Deposit is below the account's minimum deposit."""

    default_message = "Amount is below the minimum deposit."
