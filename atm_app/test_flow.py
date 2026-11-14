import json
import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from .exceptions import (
    ATMError,
    CardBlockedError,
    IncorrectPinError,
    InvalidAmountError,
    InvalidPinError,
    InsufficientFundsError,
    MinimumDepositError,
    MinimumWithdrawalError,
    WithdrawalLimitError,
)
from .atm_classes import (
    ATMService,
    Account,
    Card,
    CheckingAccount,
    SavingsAccount,
    Transaction,
    Receipt,
    _to_money,
)

D = Decimal

SAVINGS_CARD = "5000000000001001"
CHECKING_CARD = "5000000000002001"
SAVINGS_PIN = "123456"
CHECKING_PIN = "654321"

class ATMServiceCardAndReceiptTests(unittest.TestCase):

    def test_sample_cards_point_to_the_right_accounts(self):
        service = ATMService.with_sample_accounts()
        self.assertEqual(len(service.list_cards()), 2)
        self.assertEqual(service.verify_pin(SAVINGS_CARD, SAVINGS_PIN).account_number, "1001")
        self.assertEqual(service.verify_pin(CHECKING_CARD, CHECKING_PIN).account_number, "2001")

    def test_wrong_pin_is_rejected(self):
        service = ATMService.with_sample_accounts()
        with self.assertRaises(IncorrectPinError):
            service.verify_pin(SAVINGS_CARD, "000000")

    def test_unknown_card_is_rejected(self):
        with self.assertRaises(ATMError):
            ATMService.with_sample_accounts().get_card("9999")

    def test_card_for_a_missing_account_is_rejected(self):
        service = ATMService([Account("1001", "Test Holder", "1000")])
        with self.assertRaises(ATMError):
            service.add_card(Card.create("1111", "9999", "123456"))

    def test_receipt_rows_for_a_savings_withdrawal(self):
        service = ATMService.with_sample_accounts()
        t = service.withdraw("1001", "1000")
        rows = dict(service.make_receipt("1001", t).rows())
        self.assertEqual(rows["Transaction"], "Cash Withdrawal")
        self.assertEqual(rows["Amount"], "PHP 1,000.00")
        self.assertEqual(rows["Account No."], "****1001")
        self.assertEqual(rows["Current Balance"], "PHP 14,000.00")
        self.assertEqual(rows["Available Balance"], "PHP 13,500.00")   # 500 stays in savings

    def test_checking_available_balance_equals_balance(self):
        service = ATMService.with_sample_accounts()
        t = service.withdraw("2001", "1000")
        rows = dict(service.make_receipt("2001", t).rows())
        self.assertEqual(rows["Available Balance"], "PHP 24,000.00")

    def test_recent_receipts_are_newest_first(self):
        service = ATMService.with_sample_accounts()
        service.deposit("1001", "100")
        service.withdraw("1001", "200")
        kinds = [r.transaction_type for r in service.recent_receipts("1001")]
        self.assertEqual(kinds, ["Cash Withdrawal", "Cash Deposit"])

    def test_round_trip_keeps_cards(self):
        service = ATMService.with_sample_accounts()
        copy = ATMService.from_dict(json.loads(json.dumps(service.to_dict())))
        self.assertEqual(copy.verify_pin(SAVINGS_CARD, SAVINGS_PIN).account_number, "1001")

    def test_old_saved_data_without_cards_is_rejected(self):
        data = ATMService.with_sample_accounts().to_dict()
        del data["cards"]
        with self.assertRaises(KeyError):   # session_state turns this into a safe reset
            ATMService.from_dict(data)

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


class CardTests(unittest.TestCase):

    def make(self):
        return Card.create("5000000000001001", "1001", "123456")

    def test_correct_pin_passes_and_resets_attempts(self):
        card = self.make()
        with self.assertRaises(IncorrectPinError):
            card.verify_pin("000000")
        self.assertEqual(card.failed_attempts, 1)
        card.verify_pin("123456")
        self.assertEqual(card.failed_attempts, 0)

    def test_three_wrong_pins_block_the_card(self):
        card = self.make()
        with self.assertRaises(IncorrectPinError):
            card.verify_pin("000000")
        with self.assertRaises(IncorrectPinError):
            card.verify_pin("000000")
        with self.assertRaises(CardBlockedError):
            card.verify_pin("000000")
        self.assertTrue(card.is_blocked)
        with self.assertRaises(CardBlockedError):
            card.verify_pin("123456")      # right PIN, but the card is blocked

    def test_bad_pin_format_costs_no_attempt(self):
        card = self.make()
        for pin in ("123", "1234567", "abcdef", ""):
            with self.subTest(pin=pin):
                with self.assertRaises(InvalidPinError):
                    card.verify_pin(pin)
        self.assertEqual(card.failed_attempts, 0)

    def test_pin_is_never_stored(self):
        card = self.make()
        self.assertNotIn("123456", json.dumps(card.to_dict()))

    def test_change_pin(self):
        card = self.make()
        card.change_pin("123456", "111111", "111111")
        card.verify_pin("111111")
        with self.assertRaises(IncorrectPinError):
            card.verify_pin("123456")

    def test_change_pin_rejects_bad_input_and_changes_nothing(self):
        card = self.make()
        with self.assertRaises(InvalidPinError):
            card.change_pin("123456", "111111", "222222")    # PINs do not match
        with self.assertRaises(InvalidPinError):
            card.change_pin("123456", "123456", "123456")    # same as the old PIN
        with self.assertRaises(IncorrectPinError):
            card.change_pin("000000", "111111", "111111")    # wrong current PIN
        card.verify_pin("123456")                            # old PIN still works

    def test_round_trip_keeps_the_pin_and_attempts(self):
        card = self.make()
        with self.assertRaises(IncorrectPinError):
            card.verify_pin("000000")
        copy = Card.from_dict(json.loads(json.dumps(card.to_dict())))
        self.assertEqual(copy.failed_attempts, 1)
        copy.verify_pin("123456")

    def test_bad_saved_card_data_is_rejected(self):
        data = self.make().to_dict()
        for change in ({"pin_hash": "nothex"}, {"failed_attempts": 9}, {"blocked": "yes"}):
            with self.subTest(change=change):
                with self.assertRaises(ATMError):
                    Card.from_dict({**data, **change})
