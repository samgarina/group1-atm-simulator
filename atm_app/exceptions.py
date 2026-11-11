class ATMError(Exception):
    pass

class InvalidAmountError(ATMError):
    pass

class InsufficientFundsError(ATMError):
    pass