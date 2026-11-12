import json
from decimal import Decimal
from types import SimpleNamespace
import unittest

from .atm_classes import ATMService, Transaction
from .exceptions import ATMError, InvalidAmountError


D = Decimal

SAVINGS_CARD = "5000000000001001"
CHECKING_CARD = "5000000000002001"
SAVINGS_PIN = "123456"
CHECKING_PIN = "654321"

class TransactionTests(unittest.TestCase):

    def test_fields_are_stored(self):
        t = Transaction("deposit", "500", "1500")
        self.assertEqual(t.kind, "deposit")
        self.assertEqual(t.amount, D("500.00"))
        self.assertEqual(t.balance_after, D("1500.00"))

    def test_timestamp_has_no_microseconds(self):
        t = Transaction("deposit", "500", "1500")
        self.assertEqual(t.timestamp.microsecond, 0)

    def test_float_amount_is_converted_safely(self):
        t = Transaction("deposit", 0.1, 100.1)
        self.assertEqual(t.amount, D("0.10"))
        self.assertEqual(t.balance_after, D("100.10"))

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ATMError):
            Transaction("transfer", "500", "1500")

    def test_zero_and_negative_amounts_are_rejected(self):
        for amount in ("0", "-100"):
            with self.subTest(amount=amount):
                with self.assertRaises(InvalidAmountError):
                    Transaction("deposit", amount, "1500")

    def test_negative_balance_after_is_rejected(self):
        with self.assertRaises(InvalidAmountError):
            Transaction("withdrawal", "500", "-1")

    def test_bad_amount_text_is_rejected(self):
        for amount in ("abc", "", "nan", "inf", "1.234"):
            with self.subTest(amount=amount):
                with self.assertRaises(InvalidAmountError):
                    Transaction("deposit", amount, "1500")

    def test_to_dict_is_plain_json_data(self):
        data = Transaction("withdrawal", "200", "800").to_dict()
        self.assertEqual(
            set(data), {"kind", "amount", "balance_after", "timestamp"}
        )
        self.assertEqual(data["amount"], "200.00")
        json.dumps(data)  # must not raise

    def test_round_trip_keeps_every_field(self):
        original = Transaction("deposit", "500", "1500")
        copy = Transaction.from_dict(original.to_dict())
        self.assertEqual(copy.kind, original.kind)
        self.assertEqual(copy.amount, original.amount)
        self.assertEqual(copy.balance_after, original.balance_after)
        self.assertEqual(copy.timestamp, original.timestamp)

    def test_fields_are_read_only(self):
        t = Transaction("deposit", "500", "1500")
        with self.assertRaises(AttributeError):
            t.amount = 1