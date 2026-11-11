class ATMError(Exception):
    """Base class for all ATM errors in this project."""

    default_message = "An ATM error occurred."

    def __init__(self, message=None):
        # Use the given message, or fall back to the class default.
        self.message = message or self.default_message
        super().__init__(self.message)


class InvalidAmountError(ATMError):
    """Amount is zero, negative, or not a number."""

    default_message = "Invalid amount. Enter a number greater than zero."


class InsufficientFundsError(ATMError):
    """Account does not have enough money for the withdrawal."""

    default_message = "Insufficient funds for this withdrawal."