import json
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest import mock

from .atm_classes import ATMService, CheckingAccount, SavingsAccount
from .atm_flow import ATMFlow, Screen
from .exceptions import ATMError
from .session_state import FLOW_KEY, RUN_KEY, load_flow, save_flow


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

    # MenuAndLayoutTests: replaces test_every_screen_always_has_8_slots
    def test_every_screen_always_has_8_slots(self):
        """Side buttons never disappear: 4 left and 4 right on every screen."""
        service, flow = login()
        seen = set()

        def check():
            screen = flow.screen()
            seen.add(screen.name)
            self.assertEqual(len(screen.left_options()), 4, screen.name)
            self.assertEqual(len(screen.right_options()), 4, screen.name)

        withdraw(flow, "1000"); check()               # collect
        flow.finish(); check()                        # welcome
        flow.insert_card(SAVINGS_CARD); check()       # pin
        flow.submit_pin(SAVINGS_PIN); check()         # menu
        flow.choose("L1"); check()                    # balance
        flow.choose("R4"); check()                    # menu
        flow.choose("L2"); check()                    # withdraw amount
        flow.submit_amount("500"); check()            # confirm
        flow.choose("R4"); check()                    # menu (cancelled)
        flow.choose("R1"); check()                    # change pin
        flow.choose("R4"); check()                    # menu
        flow.choose("R2"); check()                    # additional
        flow.choose("L1"); check()                    # deposit amount
        flow.choose("R4"); check()                    # additional
        flow.choose("L3"); check()                    # account info
        flow.choose("R4"); check()                    # additional
        flow.choose("L2"); check()                    # mini statement
        flow.choose("L1"); check()                    # receipt view
        flow.choose("R4"); check()                    # mini statement
        flow.eject(); check()                         # collect
        self.assertEqual(len(seen), 13)

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


class BalanceTests(unittest.TestCase):

    def test_balance_inquiry_shows_three_distinct_values(self):
        _, flow = login()
        flow.choose("L1")
        screen = flow.screen()
        self.assertEqual(screen.name, "balance")
        self.assertEqual(dict(screen.rows), {
            "Current Balance": "PHP 15,000.00",
            "Available Balance": "PHP 14,500.00",
            "Maximum Withdrawal": "PHP 5,000.00",
        })
        self.assertIn("proceed", screen.message)

    def test_checking_values(self):
        _, flow = login(CHECKING_CARD, CHECKING_PIN)
        flow.choose("L1")
        self.assertEqual(dict(flow.screen().rows), {
            "Current Balance": "PHP 25,000.00",
            "Available Balance": "PHP 25,000.00",
            "Maximum Withdrawal": "PHP 20,000.00",
        })

    def test_yes_goes_to_withdrawal_without_pin_again(self):
        _, flow = login()
        flow.choose("L1")
        flow.choose("L4")  # Yes
        self.assertEqual(flow.screen_name, "withdraw_amount")
        self.assertTrue(flow.authenticated)

    def test_no_returns_to_menu(self):
        _, flow = login()
        flow.choose("L1")
        flow.choose("R4")  # No
        self.assertEqual(flow.screen_name, "menu")


class WithdrawalFlowTests(unittest.TestCase):

    # WithdrawalFlowTests: replaces test_withdrawal_screen_shows_rules
    def test_withdrawal_screen_shows_rules_but_no_balance(self):
        _, flow = login()
        flow.choose("L2")
        screen = flow.screen()
        self.assertEqual(screen.input_mode, "amount")
        self.assertEqual(screen.message, "Please enter the amount.")
        rows = dict(screen.rows)
        self.assertEqual(rows["Minimum Withdrawal"], "PHP 100.00")
        self.assertEqual(rows["Maximum Withdrawal"], "PHP 5,000.00")
        self.assertEqual(rows["In multiples of"], "PHP 100")
        self.assertNotIn("Available Balance", rows)   # balances are not shown here
        self.assertNotIn("Current Balance", rows)

    def test_invalid_amounts_keep_screen_and_balance(self):
        service, flow = login()
        cases = [
            ("", "Invalid amount. Enter a number greater than zero."),
            ("abc", "Invalid amount. Enter a number greater than zero."),
            ("-5", "Amount must be greater than zero."),
            ("0", "Amount must be greater than zero."),
            ("50", "Minimum withdrawal is PHP 100.00."),
            ("150", "Amount must be in multiples of PHP 100."),
            ("5100", "Savings accounts allow a maximum of PHP 5000.00 per withdrawal."),
            ("20000", "Insufficient funds for this withdrawal."),
        ]
        flow.choose("L2")
        for amount, message in cases:
            with self.subTest(amount=amount):
                flow.submit_amount(amount)
                self.assertEqual(flow.screen_name, "withdraw_amount")
                self.assertEqual(flow.screen().message, message)
                self.assertEqual(service.get_balance("1001"), D("15000.00"))
                self.assertEqual(service.get_history("1001"), [])

    def test_valid_amount_waits_for_confirm(self):
        service, flow = login()
        flow.choose("L2")
        flow.submit_amount("1000")
        screen = flow.screen()
        self.assertEqual(screen.name, "confirm")
        self.assertEqual(screen.message, "Withdraw PHP 1,000.00?")
        self.assertEqual(screen.left_options()[3].label, "Yes")
        self.assertEqual(screen.right_options()[3].label, "No")
        self.assertEqual(service.get_balance("1001"), D("15000.00"))  # not changed yet

    # replaces test_confirm_yes_withdraws_and_gives_receipt_and_cash
    def test_confirm_yes_withdraws_and_gives_card_receipt_and_cash(self):
        service, flow = login()
        withdraw(flow, "1000")
        screen = flow.screen()
        self.assertEqual(screen.name, "collect")
        self.assertEqual(screen.title, "TRANSACTION COMPLETE")
        self.assertIn("Transaction approved.", screen.message)
        self.assertIn("Please take your card, cash and receipt.", screen.message)
        self.assertEqual(screen.left_options(), [None] * 4)    # no follow-up question
        self.assertEqual(screen.right_options(), [None] * 4)
        self.assertTrue(flow.card_inserted)                    # the card waits in the slot
        self.assertEqual(service.get_balance("1001"), D("14000.00"))
        self.assertEqual(flow.cash_amount(), D("1000.00"))
        paper = flow.receipt_paper()
        self.assertEqual(paper.amount, D("1000.00"))
        self.assertEqual(paper.current_balance, D("14000.00"))
        self.assertEqual(paper.available_balance, D("13500.00"))

    # replaces test_second_confirm_press_does_not_withdraw_again
    def test_second_confirm_press_does_not_withdraw_again(self):
        service, flow = login()
        withdraw(flow, "1000")
        flow.choose("L4")   # the confirm button again: the screen has no buttons now
        self.assertEqual(flow.screen_name, "collect")
        self.assertEqual(flow.screen().message, "Invalid selection.")
        self.assertEqual(service.get_balance("1001"), D("14000.00"))
        self.assertEqual(len(service.get_history("1001")), 1)

    def test_confirm_no_changes_nothing(self):
        service, flow = login()
        flow.choose("L2")
        flow.submit_amount("1000")
        flow.choose("R4")  # No
        self.assertEqual(flow.screen_name, "menu")
        self.assertEqual(flow.screen().message, "Transaction cancelled.")
        self.assertEqual(service.get_balance("1001"), D("15000.00"))
        self.assertIsNone(flow.to_dict()["pending"])

    def test_cancel_key_on_confirm_changes_nothing(self):
        service, flow = login()
        flow.choose("L2")
        flow.submit_amount("1000")
        flow.cancel()
        self.assertEqual(flow.screen_name, "menu")
        self.assertEqual(service.get_balance("1001"), D("15000.00"))
        self.assertEqual(service.get_history("1001"), [])

    def test_cancel_key_on_amount_screen_returns_to_menu(self):
        service, flow = login()
        flow.choose("L2")
        flow.cancel()
        self.assertEqual(flow.screen_name, "menu")
        self.assertTrue(flow.card_inserted)

    def test_cash_and_receipt_wait_until_collected(self):
        _, flow = login()
        withdraw(flow, "1000")
        flow.cancel()                      # Cancel does nothing while items wait
        self.assertEqual(flow.screen_name, "collect")
        self.assertIsNotNone(flow.cash_amount())
        self.assertIsNotNone(flow.receipt_paper())
        flow.finish()                      # everything was taken
        self.assertEqual(flow.screen_name, "welcome")
        self.assertIsNone(flow.cash_amount())
        self.assertIsNone(flow.receipt_paper())

    # replaces test_new_transaction_replaces_receipt_paper
    def test_next_customer_gets_a_new_receipt(self):
        _, flow = login()
        withdraw(flow, "1000")
        relogin(flow)
        withdraw(flow, "500")
        self.assertEqual(flow.receipt_paper().amount, D("500.00"))
        self.assertEqual(flow.cash_amount(), D("500.00"))

    # replaces test_checking_withdrawal, and adds the declined test
    def test_checking_withdrawal(self):
        service, flow = login(CHECKING_CARD, CHECKING_PIN)
        withdraw(flow, "20000")
        self.assertEqual(flow.screen_name, "collect")
        self.assertEqual(service.get_balance("2001"), D("5000.00"))
        self.assertEqual(flow.receipt_paper().available_balance, D("5000.00"))

    def test_declined_confirm_goes_back_to_the_amount_screen(self):
        # Another request spent the money after the amount was checked.
        service, flow = login()
        flow.choose("L2")
        flow.submit_amount("5000")
        service.withdraw("1001", "5000")
        service.withdraw("1001", "5000")
        service.withdraw("1001", "4500")        # balance is now 500.00
        flow.choose("L4")                       # Yes
        self.assertEqual(flow.screen_name, "withdraw_amount")
        self.assertIn("Transaction declined.", flow.screen().message)
        self.assertEqual(service.get_balance("1001"), D("500.00"))
        self.assertTrue(flow.card_inserted)


class DepositLimitFlowTests(unittest.TestCase):
    """The deposit screen and flow enforce the PHP 20,000 limit for each deposit."""

    LIMIT_MESSAGE = "Maximum deposit is PHP 20,000.00 per transaction."

    # (card, pin, account number, starting balance)
    CUSTOMERS = (
        (SAVINGS_CARD, SAVINGS_PIN, "1001", D("15000.00")),
        (CHECKING_CARD, CHECKING_PIN, "2001", D("25000.00")),
    )

    @staticmethod
    def open_deposit(flow):
        flow.choose("R2")   # Additional Services
        flow.choose("L1")   # Cash Deposit

    def test_deposit_screen_shows_minimum_maximum_and_step(self):
        for card, pin, _, _ in self.CUSTOMERS:
            with self.subTest(card=card):
                _, flow = login(card, pin)
                self.open_deposit(flow)
                self.assertEqual(flow.screen_name, "deposit_amount")
                self.assertEqual(
                    flow.screen().rows,
                    [("Minimum Deposit", "PHP 100.00"),
                     ("Maximum Deposit", "PHP 20,000.00"),
                     ("In multiples of", "PHP 100")],
                )

    def test_displayed_maximum_comes_from_the_account(self):
        # Change the account limit. The screen must follow it (no hardcoded text).
        with mock.patch.object(SavingsAccount, "MAX_DEPOSIT", D("15000.00")):
            _, flow = login(SAVINGS_CARD, SAVINGS_PIN)
            self.open_deposit(flow)
            self.assertEqual(dict(flow.screen().rows)["Maximum Deposit"], "PHP 15,000.00")
        with mock.patch.object(CheckingAccount, "MAX_DEPOSIT", D("30000.00")):
            _, flow = login(CHECKING_CARD, CHECKING_PIN)
            self.open_deposit(flow)
            self.assertEqual(dict(flow.screen().rows)["Maximum Deposit"], "PHP 30,000.00")

    def test_over_the_limit_is_rejected_on_the_deposit_screen(self):
        for card, pin, number, start in self.CUSTOMERS:
            for amount in ("20100", "25000", "50000"):
                with self.subTest(card=card, amount=amount):
                    service, flow = login(card, pin)
                    self.open_deposit(flow)
                    flow.submit_amount(amount)
                    self.assertEqual(flow.screen_name, "deposit_amount")
                    self.assertEqual(flow.screen().message, self.LIMIT_MESSAGE)
                    self.assertIsNone(flow.to_dict()["pending"])   # never reaches confirm
                    self.assertEqual(service.get_balance(number), start)
                    self.assertEqual(service.get_history(number), [])

    def test_exactly_the_limit_goes_to_confirmation(self):
        for card, pin, number, start in self.CUSTOMERS:
            with self.subTest(card=card):
                service, flow = login(card, pin)
                self.open_deposit(flow)
                flow.submit_amount("20000")
                self.assertEqual(flow.screen_name, "confirm")
                self.assertEqual(flow.screen().message, "Deposit PHP 20,000.00?")
                self.assertEqual(service.get_balance(number), start)   # not yet changed

    def test_confirming_the_limit_deposit_updates_the_balance(self):
        for card, pin, number, start in self.CUSTOMERS:
            with self.subTest(card=card):
                service, flow = login(card, pin)
                self.open_deposit(flow)
                flow.submit_amount("20000")
                flow.choose("L4")   # Yes
                self.assertEqual(flow.screen_name, "collect")
                self.assertEqual(service.get_balance(number), start + D("20000.00"))
                self.assertEqual(len(service.get_history(number)), 1)
                receipt = flow.receipt_paper()
                self.assertEqual(receipt.transaction_type, "Cash Deposit")
                self.assertEqual(receipt.amount, D("20000.00"))

    def test_valid_deposit_works_after_a_rejected_one(self):
        service, flow = login()
        self.open_deposit(flow)
        flow.submit_amount("20100")
        self.assertEqual(flow.screen().message, self.LIMIT_MESSAGE)
        flow.submit_amount("20000")
        self.assertEqual(flow.screen_name, "confirm")
        flow.choose("L4")
        self.assertEqual(service.get_balance("1001"), D("35000.00"))
        self.assertEqual(len(service.get_history("1001")), 1)

    def test_separate_deposits_are_allowed_above_the_limit_in_total(self):
        service, flow = login()
        for _ in range(2):
            self.open_deposit(flow)
            flow.submit_amount("20000")
            flow.choose("L4")
            relogin(flow)
        self.assertEqual(service.get_balance("1001"), D("55000.00"))
        self.assertEqual(len(service.get_history("1001")), 2)

    def test_rejected_deposit_state_survives_save_and_load(self):
        service, flow = login()
        self.open_deposit(flow)
        flow.submit_amount("20100")
        restored = ATMFlow.from_dict(service, json.loads(json.dumps(flow.to_dict())))
        self.assertEqual(restored.screen_name, "deposit_amount")
        self.assertEqual(restored.screen().message, self.LIMIT_MESSAGE)
        self.assertEqual(service.get_balance("1001"), D("15000.00"))

    def test_withdrawal_screen_and_rules_are_unchanged(self):
        _, flow = login()
        flow.choose("L2")
        self.assertEqual(
            flow.screen().rows,
            [("Maximum Withdrawal", "PHP 5,000.00"),
             ("Minimum Withdrawal", "PHP 100.00"),
             ("In multiples of", "PHP 100")],
        )
        flow.submit_amount("20000")
        self.assertEqual(flow.screen_name, "withdraw_amount")   # over the savings limit


class DepositAndServicesTests(unittest.TestCase):

    # DepositAndServicesTests: replaces test_deposit_flow
    def test_deposit_flow(self):
        service, flow = login()
        flow.choose("R2")   # Additional Services
        self.assertEqual(flow.screen().title, "ADDITIONAL SERVICES")
        flow.choose("L1")   # Cash Deposit
        self.assertEqual(flow.screen_name, "deposit_amount")
        rows = dict(flow.screen().rows)
        self.assertEqual(rows["Minimum Deposit"], "PHP 100.00")
        self.assertEqual(rows["Maximum Deposit"], "PHP 20,000.00")
        self.assertEqual(rows["In multiples of"], "PHP 100")
        cases = [
            ("0", "Amount must be greater than zero."),
            ("50", "Minimum deposit is PHP 100.00."),
            ("250", "Amount must be in multiples of PHP 100."),
            ("250.50", "Amount must be in multiples of PHP 100."),
            ("20100", "Maximum deposit is PHP 20,000.00 per transaction."),
        ]
        for amount, message in cases:
            with self.subTest(amount=amount):
                flow.submit_amount(amount)
                self.assertEqual(flow.screen_name, "deposit_amount")
                self.assertEqual(flow.screen().message, message)
                self.assertEqual(service.get_balance("1001"), D("15000.00"))
        flow.submit_amount("300")
        self.assertEqual(flow.screen().message, "Deposit PHP 300.00?")
        self.assertEqual(service.get_balance("1001"), D("15000.00"))
        flow.choose("L4")
        self.assertEqual(flow.screen_name, "collect")
        self.assertIn("Please take your card and receipt.", flow.screen().message)
        self.assertNotIn("cash", flow.screen().message)
        self.assertIsNone(flow.cash_amount())           # a deposit gives no cash back
        self.assertEqual(service.get_balance("1001"), D("15300.00"))
        self.assertEqual(flow.receipt_paper().transaction_type, "Cash Deposit")

    def test_deposit_cancel_returns_to_additional_services(self):
        _, flow = login()
        flow.choose("R2")
        flow.choose("L1")
        flow.cancel()
        self.assertEqual(flow.screen_name, "additional")

    def test_mini_statement_empty(self):
        _, flow = login()
        flow.choose("R2")
        flow.choose("L2")
        screen = flow.screen()
        self.assertEqual(screen.name, "mini_statement")
        self.assertEqual(screen.message, "No transactions yet.")
        self.assertEqual(screen.left_options(), [None] * 4)

    # replaces test_mini_statement_and_receipt_view, and adds the follow-up test
    def test_mini_statement_and_receipt_view(self):
        service, flow = login()
        withdraw(flow, "1000")
        relogin(flow)
        withdraw(flow, "500")
        relogin(flow)
        flow.choose("R2")
        flow.choose("L2")
        screen = flow.screen()
        left = screen.left_options()
        self.assertEqual(left[0].label, "Cash Withdrawal 500.00")   # newest first
        self.assertEqual(left[1].label, "Cash Withdrawal 1,000.00")
        self.assertIsNone(left[2])
        self.assertTrue(left[0].sub)

        flow.choose("L2")   # open the older receipt
        screen = flow.screen()
        self.assertEqual(screen.name, "receipt_view")
        rows = dict(screen.rows)
        self.assertEqual(rows["Amount"], "PHP 1,000.00")
        self.assertEqual(rows["Current Balance"], "PHP 14,000.00")
        self.assertEqual(rows["Available Balance"], "PHP 13,500.00")
        self.assertEqual(rows["Location"], "CTU")

        flow.choose("R4")
        self.assertEqual(flow.screen_name, "mini_statement")
        flow.cancel()
        self.assertEqual(flow.screen_name, "additional")

    def test_balance_inquiry_and_services_keep_asking_for_more(self):
        """Only withdrawal and deposit end the session by themselves."""
        _, flow = login()
        flow.choose("L1")                       # Balance Inquiry asks a question
        self.assertEqual(flow.screen_name, "balance")
        flow.choose("R4")                       # No: back to the services
        self.assertEqual(flow.screen_name, "menu")
        flow.choose("R2"); flow.choose("L3")    # Account Information
        flow.choose("R4"); flow.choose("L2")    # back, then Mini Statement
        flow.choose("R4")
        self.assertEqual(flow.screen_name, "additional")
        self.assertTrue(flow.card_inserted)
        self.assertNotEqual(flow.screen().left_options(), [None] * 4)

    def test_account_information(self):
        _, flow = login()
        flow.choose("R2")
        flow.choose("L3")
        rows = dict(flow.screen().rows)
        self.assertEqual(rows["Account Type"], "Savings Account")
        self.assertEqual(rows["Account No."], "****1001")
        self.assertEqual(rows["Minimum Balance"], "PHP 500.00")
        self.assertEqual(rows["Minimum Withdrawal"], "PHP 100.00")
        self.assertEqual(rows["Maximum Withdrawal"], "PHP 5,000.00")
        self.assertEqual(rows["Minimum Deposit"], "PHP 100.00")

        _, flow = login(CHECKING_CARD, CHECKING_PIN)
        flow.choose("R2")
        flow.choose("L3")
        rows = dict(flow.screen().rows)
        self.assertEqual(rows["Minimum Balance"], "PHP 0.00")
        self.assertEqual(rows["Maximum Withdrawal"], "PHP 20,000.00")


class ChangePinFlowTests(unittest.TestCase):

    def test_change_pin_screen_has_three_prompts(self):
        _, flow = login()
        flow.choose("R1")
        screen = flow.screen()
        self.assertEqual(screen.input_mode, "change_pin")
        self.assertEqual(len(screen.prompts), 3)
        self.assertEqual(screen.message, screen.prompts[0])

    # ChangePinFlowTests: replaces test_change_pin_success
    def test_change_pin_success(self):
        service, flow = login()
        flow.choose("R1")
        flow.submit_change_pin("123456", "111222", "111222")
        self.assertEqual(flow.screen_name, "menu")
        self.assertEqual(flow.screen().message, "PIN changed successfully.")
        flow.eject()
        flow.finish()
        flow.insert_card(SAVINGS_CARD)
        flow.submit_pin("123456")                  # old PIN no longer works
        self.assertEqual(flow.screen_name, "pin")
        flow.submit_pin("111222")
        self.assertEqual(flow.screen_name, "menu")

    def test_mismatch_and_bad_format_cost_no_attempt(self):
        service, flow = login()
        flow.choose("R1")
        flow.submit_change_pin("123456", "111222", "111223")
        self.assertEqual(flow.screen_name, "change_pin")
        self.assertEqual(flow.screen().message, "PINs do not match.")
        flow.submit_change_pin("123456", "123", "123")
        self.assertEqual(flow.screen().message, "PIN must be exactly 6 digits.")
        self.assertEqual(service.get_card(SAVINGS_CARD).failed_attempts, 0)

    def test_same_pin_rejected(self):
        _, flow = login()
        flow.choose("R1")
        flow.submit_change_pin("123456", "123456", "123456")
        self.assertEqual(flow.screen().message, "New PIN must be different.")

    def test_wrong_current_pin_blocks_card_after_three(self):
        service, flow = login()
        flow.choose("R1")
        flow.submit_change_pin("000000", "111222", "111222")
        self.assertEqual(flow.screen().message, "Incorrect PIN. Please try again.")
        flow.submit_change_pin("000000", "111222", "111222")
        self.assertEqual(flow.screen().message, "Incorrect PIN. Last attempt remaining.")
        flow.submit_change_pin("000000", "111222", "111222")
        self.assertEqual(flow.screen_name, "welcome")
        self.assertIn("Card blocked.", flow.screen().message)
        self.assertTrue(service.get_card(SAVINGS_CARD).is_blocked)

    def test_change_pin_out_of_step(self):
        _, flow = login()
        flow.submit_change_pin("123456", "111222", "111222")
        self.assertEqual(flow.screen_name, "menu")
        self.assertEqual(flow.screen().message, "Please follow the instructions on the screen.")

    def test_change_pin_state_has_no_pins(self):
        _, flow = login()
        flow.choose("R1")
        flow.submit_change_pin("123456", "111222", "111223")
        text = json.dumps(flow.to_dict())
        for pin in ("123456", "111222", "111223"):
            self.assertNotIn(pin, text)


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


class SavedStateTests(unittest.TestCase):

    def test_round_trip_in_the_middle_of_a_transaction(self):
        service, flow = login()
        flow.choose("L2")
        flow.submit_amount("1000")
        data = json.loads(json.dumps(flow.to_dict()))   # must be plain JSON data
        flow2 = ATMFlow.from_dict(service, data)
        self.assertEqual(flow2.screen().message, "Withdraw PHP 1,000.00?")
        flow2.choose("L4")
        self.assertEqual(service.get_balance("1001"), D("14000.00"))

    def test_bad_saved_flow_data_is_rejected(self):
        service, flow = login()
        flow.choose("L2")
        flow.submit_amount("1000")
        good = flow.to_dict()

        bad_changes = [
            {"screen": "nope"},
            {"screen": "welcome"},                      # card still set
            {"card": "9999"},                           # unknown card
            {"authed": False},                          # confirm needs authed
            {"authed": "yes"},
            {"pending": None},                          # confirm needs pending
            {"pending": {"kind": "steal", "amount": "5"}},
            {"pending": {"kind": "withdrawal", "amount": "abc"}},
            {"pending": {"kind": "withdrawal", "amount": "-5"}},
            {"message": 5},
            {"message": "x" * 301},
            {"cash": "100.00"},                         # cash only on the collect screen
            {"view_index": 0},                          # only on receipt_view
            {"receipt_ready": "no"},
            {"receipt_ready": True}                     # slip only on the collect screen to bad_changes
        ]
        for change in bad_changes:
            with self.subTest(change=change):
                with self.assertRaises(ATMError):
                    ATMFlow.from_dict(service, {**good, **change})

        with self.assertRaises(ATMError):
            ATMFlow.from_dict(service, {})
        with self.assertRaises(ATMError):
            ATMFlow.from_dict(service, "garbage")

    def test_blocked_card_cannot_be_inside_a_session(self):
        service, flow = login()
        for _ in range(3):
            try:
                service.get_card(SAVINGS_CARD).verify_pin("000000")
            except ATMError:
                pass
        with self.assertRaises(ATMError):
            ATMFlow.from_dict(service, flow.to_dict())

    def test_receipt_view_index_must_exist(self):
        service, flow = login()
        withdraw(flow, "1000")
        relogin(flow)
        flow.choose("R2")
        flow.choose("L2")
        flow.choose("L1")
        good = flow.to_dict()
        self.assertEqual(good["view_index"], 0)
        with self.assertRaises(ATMError):
            ATMFlow.from_dict(service, {**good, "view_index": 3})
        with self.assertRaises(ATMError):
            ATMFlow.from_dict(service, {**good, "view_index": True})

    def test_collect_state_round_trip_and_rules(self):
        service, flow = login()
        withdraw(flow, "1000")
        good = json.loads(json.dumps(flow.to_dict()))
        self.assertEqual(good["screen"], "collect")
        again = ATMFlow.from_dict(service, good)
        self.assertEqual(again.cash_amount(), D("1000.00"))
        self.assertEqual(again.receipt_paper().amount, D("1000.00"))
        again.finish()
        self.assertEqual(again.screen_name, "welcome")

        bad_changes = [
            {"receipt_ready": False},                   # cash needs a receipt
            {"authed": False},                          # a slip needs a finished transaction
            {"cash": "0.00"},
            {"cash": "abc"},
            {"card": ""},                               # the card must be in the slot
        ]
        for change in bad_changes:
            with self.subTest(change=change):
                with self.assertRaises(ATMError):
                    ATMFlow.from_dict(service, {**good, **change})

    def test_card_only_collect_state_is_valid(self):
        service, flow = login()
        flow.eject()
        ATMFlow.from_dict(service, flow.to_dict())      # no exception


class SessionHelperTests(unittest.TestCase):
    """load_flow and save_flow work with any request that has a dict-like session."""

    def fake_request(self):
        return SimpleNamespace(session={})

    def test_no_saved_flow_starts_at_welcome(self):
        service = ATMService.with_sample_accounts()
        flow = load_flow(self.fake_request(), service)
        self.assertEqual(flow.screen_name, "welcome")

    def test_save_and_load(self):
        service, flow = login()
        request = self.fake_request()
        save_flow(request, flow)
        self.assertEqual(request.session[FLOW_KEY], flow.to_dict())
        json.dumps(request.session[FLOW_KEY])            # plain data only
        loaded = load_flow(request, service)
        self.assertEqual(loaded.screen_name, "menu")
        self.assertTrue(loaded.authenticated)

    def test_bad_saved_flow_resets_to_welcome(self):
        service = ATMService.with_sample_accounts()
        request = self.fake_request()
        request.session[FLOW_KEY] = {"screen": "menu"}
        flow = load_flow(request, service)
        self.assertEqual(flow.screen_name, "welcome")
        self.assertEqual(service.get_balance("1001"), D("15000.00"))

    def test_flow_from_an_earlier_run_is_dropped(self):
        """After the web app restarts, the ATM starts at the welcome screen again."""
        service, flow = login()
        request = self.fake_request()
        save_flow(request, flow)
        self.assertEqual(load_flow(request, service).screen_name, "menu")
        request.session[RUN_KEY] = "an-earlier-run"
        self.assertEqual(load_flow(request, service).screen_name, "welcome")
        self.assertEqual(service.get_balance("1001"), D("15000.00"))   # balances stay

    def test_saved_flow_is_small(self):
        service, flow = login()
        withdraw(flow, "1000")
        self.assertLess(len(json.dumps(flow.to_dict())), 500)