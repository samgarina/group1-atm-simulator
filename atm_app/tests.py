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

# tests.py
class AccountBasicsTests(unittest.TestCase):
    """Goals 3, 4, 5 on the parent class."""
    
    def setUp(self):
        # Initializes with account number, owner, and starting balance
        self.acc = Account("001", "Ana", "1000")

    def test_balance_read_only(self):
        # Checks that attempting to directly modify the balance throws an AttributeError
        with self.assertRaises(AttributeError):
            self.acc.balance = D("1")


class MoneyTests(unittest.TestCase):
    """Goal 6: Decimal accuracy and input cleaning."""

    def test_float_is_exact(self):
        self.assertEqual(_to_money(0.1) + _to_money(0.2), D("0.30"))

    def test_always_two_places(self):
        self.assertEqual(str(_to_money("5.5")), "5.50")
        self.assertEqual(str(_to_money(7)), "7.00")

    def test_bad_values_rejected(self):
        for bad in ["abc", "", None, "NaN", "Infinity", "-Infinity", "1.234", True]:
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidAmountError):
                    _to_money(bad)

    def test_huge_value_rejected_cleanly(self):
        with self.assertRaises(InvalidAmountError):
            _to_money("1" * 40)

    