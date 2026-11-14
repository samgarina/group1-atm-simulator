import json
import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from .atm_flow import ATMFlow, Screen
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



def make():
    """New service and flow. The flow is at the welcome screen."""
    service = ATMService.with_sample_accounts()
    return service, ATMFlow(service)


def login(card=SAVINGS_CARD, pin=SAVINGS_PIN):
    """New service and flow, already at the ATM SERVICES menu."""
    service, flow = make()
    flow.insert_card(card)
    flow.submit_pin(pin)
    return service, flow


def withdraw(flow, amount):
    """Menu to the collect screen using the side buttons."""
    flow.choose("L2")            # Cash Withdrawal
    flow.submit_amount(amount)
    flow.choose("L4")            # Yes


def relogin(flow, card=SAVINGS_CARD, pin=SAVINGS_PIN):
    """Take the card, then insert it again. For the next customer."""
    flow.finish()
    flow.insert_card(card)
    flow.submit_pin(pin)



class WelcomeAndCardTests(unittest.TestCase):

    def test_welcome_screen(self):
        _, flow = make()
        screen = flow.screen()
        self.assertEqual(screen.name, "welcome")
        self.assertIn("Welcome to PELEC Bank.", screen.message)
        self.assertIn("Please insert your ATM card.", screen.message)
        self.assertEqual(screen.options, {})
        self.assertFalse(flow.card_inserted)

    def test_unknown_card(self):
        _, flow = make()
        flow.insert_card("9999")
        self.assertEqual(flow.screen_name, "welcome")
        self.assertEqual(flow.screen().message, "Card not found.")

    def test_card_goes_to_pin_screen(self):
        _, flow = make()
        flow.insert_card(SAVINGS_CARD)
        screen = flow.screen()
        self.assertEqual(screen.name, "pin")
        self.assertEqual(screen.input_mode, "pin")
        self.assertEqual(screen.message, "Please enter your six-digit PIN.")
        self.assertTrue(flow.card_inserted)
        self.assertFalse(flow.authenticated)

    def test_blocked_card_is_refused(self):
        service, flow = make()
        for _ in range(3):
            flow.insert_card(SAVINGS_CARD)
            flow.submit_pin("000000")
        flow.insert_card(SAVINGS_CARD)
        self.assertEqual(flow.screen_name, "welcome")
        self.assertIn("This card is blocked.", flow.screen().message)



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


class PinTests(unittest.TestCase):

    def test_wrong_pin_messages_then_block(self):
        service, flow = make()
        flow.insert_card(SAVINGS_CARD)

        flow.submit_pin("000000")
        self.assertEqual(flow.screen_name, "pin")
        self.assertEqual(flow.screen().message, "Incorrect PIN. Please try again.")

        flow.submit_pin("000000")
        self.assertEqual(flow.screen().message, "Incorrect PIN. Last attempt remaining.")

        flow.submit_pin("000000")
        self.assertEqual(flow.screen_name, "welcome")
        self.assertIn("Card blocked.", flow.screen().message)
        self.assertIn("Please contact your bank.", flow.screen().message)
        self.assertTrue(service.get_card(SAVINGS_CARD).is_blocked)
        self.assertFalse(flow.card_inserted)
        self.assertFalse(flow.authenticated)

    def test_bad_format_costs_no_attempt(self):
        service, flow = make()
        flow.insert_card(SAVINGS_CARD)
        flow.submit_pin("123")
        self.assertEqual(flow.screen_name, "pin")
        self.assertEqual(flow.screen().message, "PIN must be exactly 6 digits.")
        self.assertEqual(service.get_card(SAVINGS_CARD).failed_attempts, 0)

    def test_correct_pin_opens_menu(self):
        _, flow = login()
        screen = flow.screen()
        self.assertEqual(screen.name, "menu")
        self.assertEqual(screen.title, "ATM SERVICES")
        self.assertEqual(screen.message, "Please select a service.")
        self.assertTrue(flow.authenticated)

    # PinTests: replaces test_cancel_on_pin_screen_removes_card
    def test_cancel_on_pin_screen_returns_the_card(self):
        _, flow = make()
        flow.insert_card(SAVINGS_CARD)
        flow.cancel()
        self.assertEqual(flow.screen_name, "collect")
        self.assertEqual(flow.screen().message, "Please take your card.")
        self.assertTrue(flow.card_inserted)      # the card waits in the slot
        flow.finish()
        self.assertEqual(flow.screen_name, "welcome")
        self.assertFalse(flow.card_inserted)
        self.assertIn("Please insert your card.", flow.screen().message)

    def test_input_out_of_step_is_ignored(self):
        service, flow = make()
        before = flow.to_dict()
        flow.submit_pin(SAVINGS_PIN)         # no card yet
        self.assertEqual(flow.screen_name, "welcome")
        self.assertFalse(flow.authenticated)
        flow.submit_amount("1000")
        flow.choose("L1")
        self.assertEqual(flow.screen_name, "welcome")
        self.assertEqual(flow.to_dict()["card"], before["card"])

        _, flow = login()
        flow.submit_amount("1000")           # menu does not take amounts
        self.assertEqual(flow.screen_name, "menu")
        self.assertEqual(flow.screen().message, "Please follow the instructions on the screen.")
        flow.submit_pin(SAVINGS_PIN)
        self.assertEqual(flow.screen_name, "menu")
        flow.insert_card(CHECKING_CARD)
        self.assertEqual(flow.screen_name, "menu")

    def test_pin_is_not_in_saved_state(self):
        _, flow = make()
        flow.insert_card(SAVINGS_CARD)
        flow.submit_pin(SAVINGS_PIN)
        self.assertNotIn(SAVINGS_PIN, json.dumps(flow.to_dict()))



class MenuAndLayoutTests(unittest.TestCase):

    def test_menu_options_in_fixed_slots(self):
        _, flow = login()
        screen = flow.screen()
        left, right = screen.left_options(), screen.right_options()
        self.assertEqual(left[0].label, "Balance Inquiry")
        self.assertEqual(left[1].label, "Cash Withdrawal")
        self.assertEqual(right[0].label, "Change PIN")
        self.assertEqual(right[1].label, "Additional Services")
        self.assertEqual(right[3].label, "Exit")
        self.assertIsNone(left[2])
        self.assertIsNone(left[3])
        self.assertIsNone(right[2])

    def test_empty_slot_is_ignored(self):
        _, flow = login()
        flow.choose("L4")
        self.assertEqual(flow.screen_name, "menu")
        self.assertEqual(flow.screen().message, "Invalid selection.")
        flow.choose("X9")
        self.assertEqual(flow.screen().message, "Invalid selection.")


    def test_screen_class_pads_to_four(self):
        screen = Screen("x", "T", "m")
        self.assertEqual(screen.left_options(), [None] * 4)
        self.assertEqual(screen.right_options(), [None] * 4)



class ExitTests(unittest.TestCase):

    def test_exit_button_returns_the_card(self):
        _, flow = login()
        flow.choose("R4")   # Exit
        screen = flow.screen()
        self.assertEqual(screen.name, "collect")
        self.assertEqual(screen.title, "THANK YOU")
        self.assertEqual(screen.message, "Please take your card.")
        self.assertTrue(flow.card_inserted)         # the card waits in the slot
        self.assertIsNone(flow.receipt_paper())
        self.assertIsNone(flow.cash_amount())
        self.assertEqual(screen.left_options(), [None] * 4)
        self.assertEqual(screen.right_options(), [None] * 4)

    def test_taking_the_card_goes_back_to_welcome_with_insert_card_message(self):
        _, flow = login()
        flow.eject()
        flow.finish()
        self.assertEqual(flow.screen_name, "welcome")
        self.assertFalse(flow.card_inserted)
        self.assertFalse(flow.authenticated)
        self.assertEqual(
            flow.screen().message,
            "Thank you for using PELEC Bank.\nPlease insert your card.",
        )

    def test_cancel_key_on_menu_returns_the_card(self):
        _, flow = login()
        flow.cancel()
        self.assertEqual(flow.screen_name, "collect")

    def test_nothing_works_while_the_card_waits(self):
        service, flow = login()
        flow.eject()
        flow.cancel()                                # Cancel does nothing here
        flow.choose("L2")                            # no buttons on this screen
        flow.submit_amount("1000")
        flow.submit_pin(SAVINGS_PIN)
        flow.insert_card(CHECKING_CARD)              # a card is already in the slot
        self.assertEqual(flow.screen_name, "collect")
        self.assertEqual(service.get_history("1001"), [])

    def test_eject_twice_changes_nothing(self):
        _, flow = login()
        flow.eject()
        state = flow.to_dict()
        flow.eject()
        self.assertEqual(flow.to_dict(), state)

    def test_finish_outside_the_collect_screen_is_ignored(self):
        _, flow = login()
        flow.finish()
        self.assertEqual(flow.screen_name, "menu")
        self.assertTrue(flow.authenticated)
        self.assertEqual(flow.screen().message, "Please follow the instructions on the screen.")

        _, flow = make()
        flow.finish()
        self.assertEqual(flow.screen_name, "welcome")

    def test_balance_survives_the_session_end(self):
        service, flow = login()
        withdraw(flow, "1000")
        relogin(flow)
        flow.choose("L1")
        self.assertEqual(dict(flow.screen().rows)["Current Balance"], "PHP 14,000.00")

    def test_blocked_card_is_kept_by_the_machine(self):
        """A blocked card is not given back: the session ends at the welcome screen."""
        _, flow = make()
        flow.insert_card(SAVINGS_CARD)
        for _ in range(3):
            flow.submit_pin("000000")
        self.assertEqual(flow.screen_name, "welcome")
        self.assertFalse(flow.card_inserted)


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
