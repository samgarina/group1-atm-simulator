from django.test import TestCase

# Create your tests here.
import json
import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from .exceptions import (
    ATMError,
    InvalidAmountError,
    InsufficientFundsError,
    WithdrawalLimitError,
)

from .atm_classes import (
    ATMService, Account, Card, CheckingAccount, Receipt, SavingsAccount, Transaction,
    _to_money,
)

D = Decimal

class AccountBasicsTests(unittest.TestCase):
    """Goals 3, 4, 5 on the parent class."""
    
    def setUp(self):
        # Initializes with account number, owner, and starting balance
        self.acc = Account("001", "Ana", "1000")

    def test_balance_read_only(self):
        # Checks that attempting to directly modify the balance throws an AttributeError
        with self.assertRaises(AttributeError):
            self.acc.balance = D("1")