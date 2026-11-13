import json
from decimal import Decimal
from types import SimpleNamespace
import unittest

from .atm_classes import Account, ATMService, SavingsAccount, Transaction
from .exceptions import (
    ATMError,
    InsufficientFundsError,
    InvalidAmountError,
    WithdrawalLimitError,
)

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














class ATMServiceDepositTests(unittest.TestCase):

    def make(self):
        return ATMService([Account("1001", "Test Holder", "1000")])

    def test_deposit_records_a_transaction(self):
        service = self.make()
        t = service.deposit("1001", "500")
        self.assertIsInstance(t, Transaction)
        self.assertEqual(t.kind, "deposit")
        self.assertEqual(t.amount, D("500.00"))
        self.assertEqual(t.balance_after, D("1500.00"))
        self.assertEqual(service.get_balance("1001"), D("1500.00"))
        self.assertEqual(service.get_account("1001").transactions, [t])

    def test_account_number_works_as_text_or_number(self):
        service = self.make()
        service.deposit(1001, "100")
        self.assertEqual(service.get_balance("1001"), D("1100.00"))

    def test_invalid_deposit_changes_nothing(self):
        # zero, negative, text, below the minimum, not a multiple of 100
        for amount in ("0", "-100", "abc", "50", "150"):
            with self.subTest(amount=amount):
                service = self.make()
                with self.assertRaises(ATMError):
                    service.deposit("1001", amount)
                self.assertEqual(service.get_balance("1001"), D("1000.00"))
                self.assertEqual(service.get_account("1001").transactions, [])

    def test_unknown_account_is_rejected(self):
        with self.assertRaises(ATMError):
            self.make().deposit("9999", "100")

    def test_duplicate_account_number_is_rejected(self):
        service = self.make()
        with self.assertRaises(ATMError):
            service.add_account(Account("1001", "Another Holder", "0"))

    def test_list_accounts(self):
        self.assertEqual(len(self.make().list_accounts()), 1)

class ATMServiceWithdrawTests(unittest.TestCase):

    def test_sample_accounts(self):
        service = ATMService.with_sample_accounts()
        self.assertEqual(len(service.list_accounts()), 2)
        self.assertEqual(service.get_account("1001").account_type, "Savings Account")
        self.assertEqual(service.get_account("2001").account_type, "Checking Account")
        self.assertEqual(service.get_balance("1001"), D("15000.00"))
        self.assertEqual(service.get_balance("2001"), D("25000.00"))

    def test_withdraw_records_a_transaction(self):
        service = ATMService.with_sample_accounts()
        t = service.withdraw("1001", "1000")
        self.assertEqual(t.kind, "withdrawal")
        self.assertEqual(t.balance_after, D("14000.00"))
        self.assertEqual(service.get_balance("1001"), D("14000.00"))
        self.assertEqual(service.get_history("1001"), [t])

    def test_same_withdraw_call_gives_different_results(self):
        """Polymorphism: Savings has a lower limit than Checking."""
        service = ATMService.with_sample_accounts()
        with self.assertRaises(WithdrawalLimitError):
            service.withdraw("1001", "6000")               # Savings
        t = service.withdraw("2001", "6000")               # Checking
        self.assertEqual(t.balance_after, D("19000.00"))

    def test_failed_withdrawal_keeps_balance_and_history(self):
        # negative, text, below minimum, not a multiple of 100,
        # over the balance, below the savings minimum balance
        for amount in ("-100", "abc", "50", "150", "20000", "14600"):
            with self.subTest(amount=amount):
                service = ATMService.with_sample_accounts()
                with self.assertRaises(ATMError):
                    service.withdraw("1001", amount)
                self.assertEqual(service.get_balance("1001"), D("15000.00"))
                self.assertEqual(service.get_history("1001"), [])

    def test_savings_boundary_at_the_minimum_balance(self):
        service = ATMService([SavingsAccount("3001", "Test Holder", "5500")])
        t = service.withdraw("3001", "5000")               # leaves exactly 500
        self.assertEqual(t.balance_after, D("500.00"))
        with self.assertRaises(InsufficientFundsError):
            service.withdraw("3001", "100")                # would go below 500
        self.assertEqual(service.get_balance("3001"), D("500.00"))

    def test_history_is_oldest_first_and_cannot_be_edited(self):
        service = ATMService.with_sample_accounts()
        first = service.deposit("1001", "500")
        second = service.withdraw("1001", "300")
        history = service.get_history("1001")
        self.assertEqual(history, [first, second])
        history.append("junk")                             # change the copy only
        self.assertEqual(service.get_history("1001"), [first, second])