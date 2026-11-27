import json
import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.sessions.backends.signed_cookies import SessionStore

from .atm_classes import (
    ATMService, Account, Card, CheckingAccount, Receipt, SavingsAccount, Transaction,
    _to_money,
)

from .exceptions import (
    ATMError, CardBlockedError, DepositLimitError, IncorrectPinError, InsufficientFundsError,
    InvalidAmountError, InvalidPinError, MinimumDepositError, MinimumWithdrawalError,
    WithdrawalLimitError,
)

from .session_state import SESSION_KEY, load_service, save_service



D = Decimal


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

    def test_ten_small_deposits_no_drift(self):
        acc = CheckingAccount("1", "A", "0")
        for _ in range(10):
            acc.deposit("100")
        self.assertEqual(acc.balance, D("1000"))


class TransactionTests(unittest.TestCase):
    def test_round_trip(self):
        t = Transaction("deposit", "10", "110")
        t2 = Transaction.from_dict(t.to_dict())
        self.assertEqual(t2.to_dict(), t.to_dict())
        self.assertIsInstance(t2.timestamp, datetime)

    def test_bad_kind(self):
        with self.assertRaises(ATMError):
            Transaction("transfer", "10", "10")

    def test_bad_amounts(self):
        for amt in ["0", "-1"]:
            with self.assertRaises(InvalidAmountError):
                Transaction("deposit", amt, "10")
        with self.assertRaises(InvalidAmountError):
            Transaction("deposit", "1", "-1")

    def test_read_only(self):
        t = Transaction("deposit", "10", "110")
        with self.assertRaises(AttributeError):
            t.amount = D("999")


class AccountBasicsTests(unittest.TestCase):
    """Goals 3, 4, 5 on the parent class."""

    def setUp(self):
        self.acc = Account("001", "Ana", "1000")

    def test_balances_and_history(self):
        self.acc.deposit("300")
        self.acc.withdraw("100")
        self.assertEqual(self.acc.balance, D("1200"))
        kinds = [t.kind for t in self.acc.transactions]
        self.assertEqual(kinds, ["deposit", "withdrawal"])
        self.assertEqual([t.balance_after for t in self.acc.transactions],
                         [D("1300.00"), D("1200.00")])

    def test_invalid_keeps_state(self):
        for amt in ["-5", "0", "abc", "1.999", None]:
            with self.subTest(amt=amt):
                with self.assertRaises(InvalidAmountError):
                    self.acc.deposit(amt)
                with self.assertRaises(InvalidAmountError):
                    self.acc.withdraw(amt)
        with self.assertRaises(InsufficientFundsError):
            self.acc.withdraw("1100")
        self.assertEqual(self.acc.balance, D("1000.00"))
        self.assertEqual(self.acc.transactions, [])

    def test_withdraw_all_boundary(self):
        self.acc.withdraw("1000")
        self.assertEqual(self.acc.balance, D("0.00"))

    def test_history_is_copy(self):
        self.acc.deposit("100")
        self.acc.transactions.clear()
        self.assertEqual(len(self.acc.transactions), 1)

    def test_balance_read_only(self):
        with self.assertRaises(AttributeError):
            self.acc.balance = D("1")

    def test_bad_construction(self):
        with self.assertRaises(ATMError):
            Account("2", "   ")
        with self.assertRaises(InvalidAmountError):
            Account("2", "Bo", "-1")


class SavingsRuleTests(unittest.TestCase):
    """Goal 2: savings keeps PHP 500 minimum."""

    def setUp(self):
        self.acc = SavingsAccount("S1", "Maria", "1000")

    def test_withdraw_to_exact_minimum_ok(self):
        self.acc.withdraw("500")
        self.assertEqual(self.acc.balance, D("500.00"))

    def test_below_minimum_balance_rejected(self):
        # 1000 - 600 = 400, which is below the PHP 500 minimum balance.
        with self.assertRaises(InsufficientFundsError):
            self.acc.withdraw("600")
        self.assertEqual(self.acc.balance, D("1000.00"))
        self.assertEqual(self.acc.transactions, [])

    def test_opening_below_minimum_rejected(self):
        with self.assertRaises(InvalidAmountError):
            SavingsAccount("S2", "Pat", "499.99")

    def test_deposit_then_withdraw(self):
        self.acc.deposit("200")
        self.acc.withdraw("700")
        self.assertEqual(self.acc.balance, D("500.00"))

    def test_invalid_amount_still_rejected(self):
        with self.assertRaises(InvalidAmountError):
            self.acc.withdraw("-1")

    def test_max_withdrawal_limit(self):
        rich = SavingsAccount("S3", "Rica", "20000")
        rich.withdraw("5000")  # exactly the limit is allowed
        self.assertEqual(rich.balance, D("15000.00"))
        with self.assertRaises(WithdrawalLimitError):
            rich.withdraw("5100")
        self.assertEqual(rich.balance, D("15000.00"))
        self.assertEqual(len(rich.transactions), 1)

    def test_available_balance(self):
        # Available balance = balance - minimum balance. Never below zero.
        self.assertEqual(self.acc.available_balance, D("500.00"))
        self.acc.withdraw("500")
        self.assertEqual(self.acc.available_balance, D("0.00"))

    


class CheckingRuleTests(unittest.TestCase):
    """Goal 2: checking has PHP 10,000 per-withdrawal limit."""

    def setUp(self):
        self.acc = CheckingAccount("C1", "Juan", "25000")

    def test_exact_limit_ok(self):
        self.acc.withdraw("20000")
        self.assertEqual(self.acc.balance, D("5000.00"))

    def test_above_limit_rejected(self):
        with self.assertRaises(WithdrawalLimitError):
            self.acc.withdraw("20100")
        self.assertEqual(self.acc.balance, D("25000.00"))
        self.assertEqual(self.acc.transactions, [])

    def test_can_go_to_zero(self):
        self.acc.withdraw("10000")
        self.acc.withdraw("10000")
        self.acc.withdraw("5000")
        self.assertEqual(self.acc.balance, D("0.00"))

    def test_overdraft_under_limit(self):
        poor = CheckingAccount("C2", "Lia", "100")
        with self.assertRaises(InsufficientFundsError):
            poor.withdraw("200")
        self.assertEqual(poor.balance, D("100.00"))

    def test_limit_error_is_atm_error(self):
        with self.assertRaises(ATMError):
            self.acc.withdraw("20100")

    def test_available_balance_equals_balance(self):
        # Checking has no minimum balance.
        self.assertEqual(self.acc.available_balance, D("25000.00"))

class CommonWithdrawalRuleTests(unittest.TestCase):
    """Rules from Account.check_withdrawal(). Every account type has them."""

    def test_below_minimum_withdrawal(self):
        for acc in (SavingsAccount("S", "A", "5000"), CheckingAccount("C", "B", "5000")):
            with self.subTest(acc=acc.account_type):
                with self.assertRaises(MinimumWithdrawalError):
                    acc.withdraw("50")
                self.assertEqual(acc.balance, D("5000.00"))

    def test_minimum_withdrawal_boundary(self):
        for acc in (SavingsAccount("S", "A", "5000"), CheckingAccount("C", "B", "5000")):
            with self.subTest(acc=acc.account_type):
                acc.withdraw("100")
                self.assertEqual(acc.balance, D("4900.00"))

    def test_not_multiple_of_bill_step(self):
        for amount in ("150", "100.50", "101"):
            for acc in (SavingsAccount("S", "A", "5000"), CheckingAccount("C", "B", "5000")):
                with self.subTest(acc=acc.account_type, amount=amount):
                    with self.assertRaises(InvalidAmountError):
                        acc.withdraw(amount)
                    self.assertEqual(acc.balance, D("5000.00"))
                    self.assertEqual(acc.transactions, [])

    def test_check_withdrawal_changes_nothing(self):
        acc = CheckingAccount("C", "B", "5000")
        self.assertEqual(acc.check_withdrawal("1000"), D("1000.00"))
        self.assertEqual(acc.balance, D("5000.00"))
        self.assertEqual(acc.transactions, [])
        with self.assertRaises(WithdrawalLimitError):
            CheckingAccount("C2", "B", "50000").check_withdrawal("20100")

class DepositRuleTests(unittest.TestCase):
    """Deposits: at least PHP 100, in multiples of PHP 100, no coins."""

    def accounts(self):
        return (SavingsAccount("S", "A", "5000"), CheckingAccount("C", "B", "5000"))

    def test_below_minimum_deposit(self):
        for acc in self.accounts():
            with self.subTest(acc=acc.account_type):
                with self.assertRaises(MinimumDepositError) as ctx:
                    acc.deposit("50")
                self.assertEqual(ctx.exception.message, "Minimum deposit is PHP 100.00.")
                self.assertEqual(acc.balance, D("5000.00"))
                self.assertEqual(acc.transactions, [])

    def test_minimum_deposit_boundary(self):
        for acc in self.accounts():
            with self.subTest(acc=acc.account_type):
                acc.deposit("100")
                self.assertEqual(acc.balance, D("5100.00"))

    def test_deposit_must_be_multiple_of_bill_step(self):
        for amount in ("150", "250.50", "100.50", "101", "20.25"):
            for acc in self.accounts():
                with self.subTest(acc=acc.account_type, amount=amount):
                    with self.assertRaises((InvalidAmountError, MinimumDepositError)):
                        acc.deposit(amount)
                    self.assertEqual(acc.balance, D("5000.00"))
                    self.assertEqual(acc.transactions, [])

    def test_multiple_of_bill_step_message(self):
        acc = CheckingAccount("C", "B", "0")
        with self.assertRaises(InvalidAmountError) as ctx:
            acc.deposit("250")
        self.assertEqual(ctx.exception.message, "Amount must be in multiples of PHP 100.")

    def test_large_deposit_in_whole_bills_is_allowed(self):
        # A big deposit is fine while it stays at or under the PHP 20,000 limit.
        for acc in (SavingsAccount("S", "A", "500"), CheckingAccount("C", "B", "500")):
            with self.subTest(acc=acc.account_type):
                acc.deposit("19900")
                self.assertEqual(acc.balance, D("20400.00"))

    def test_check_deposit_changes_nothing(self):
        acc = CheckingAccount("C", "B", "5000")
        self.assertEqual(acc.check_deposit("300"), D("300.00"))
        self.assertEqual(acc.balance, D("5000.00"))
        self.assertEqual(acc.transactions, [])
        with self.assertRaises(MinimumDepositError):
            acc.check_deposit("99")

class DepositLimitTests(unittest.TestCase):
    """One deposit cannot be above PHP 20,000. The limit is not on the total balance."""

    LIMIT_MESSAGE = "Maximum deposit is PHP 20,000.00 per transaction."

    def accounts(self, balance="5000"):
        return (SavingsAccount("S", "A", balance), CheckingAccount("C", "B", balance))

    def test_each_account_class_defines_its_own_limit(self):
        self.assertEqual(SavingsAccount.MAX_DEPOSIT, D("20000.00"))
        self.assertEqual(CheckingAccount.MAX_DEPOSIT, D("20000.00"))
        # vars() shows only what the class itself defines, not what it inherits.
        self.assertIn("MAX_DEPOSIT", vars(SavingsAccount))
        self.assertIn("MAX_DEPOSIT", vars(CheckingAccount))

    def test_exactly_the_limit_is_accepted(self):
        for acc in self.accounts():
            with self.subTest(acc=acc.account_type):
                transaction = acc.deposit("20000")
                self.assertEqual(transaction.amount, D("20000.00"))
                self.assertEqual(acc.balance, D("25000.00"))
                self.assertEqual(len(acc.transactions), 1)

    def test_check_deposit_accepts_exactly_the_limit(self):
        for acc in self.accounts():
            with self.subTest(acc=acc.account_type):
                self.assertEqual(acc.check_deposit("20000"), D("20000.00"))

    def test_above_the_limit_is_rejected_by_deposit(self):
        for amount in ("20100", "25000", "50000", "20000.01"):
            for acc in self.accounts():
                with self.subTest(acc=acc.account_type, amount=amount):
                    with self.assertRaises(DepositLimitError) as ctx:
                        acc.deposit(amount)
                    self.assertEqual(ctx.exception.message, self.LIMIT_MESSAGE)
                    self.assertEqual(acc.balance, D("5000.00"))
                    self.assertEqual(acc.transactions, [])

    def test_above_the_limit_is_rejected_by_check_deposit(self):
        for amount in ("20100", "50000"):
            for acc in self.accounts():
                with self.subTest(acc=acc.account_type, amount=amount):
                    with self.assertRaises(DepositLimitError):
                        acc.check_deposit(amount)

    def test_check_deposit_changes_nothing(self):
        for acc in self.accounts():
            with self.subTest(acc=acc.account_type):
                acc.check_deposit("20000")
                with self.assertRaises(DepositLimitError):
                    acc.check_deposit("20100")
                self.assertEqual(acc.balance, D("5000.00"))
                self.assertEqual(acc.transactions, [])

    def test_limit_is_per_transaction_not_for_the_balance(self):
        for acc in self.accounts("500"):
            with self.subTest(acc=acc.account_type):
                for _ in range(3):
                    acc.deposit("20000")
                self.assertEqual(acc.balance, D("60500.00"))
                self.assertEqual(len(acc.transactions), 3)
                acc.deposit("100")  # still fine with a balance above the limit
                self.assertEqual(acc.balance, D("60600.00"))

    def test_account_opens_with_a_balance_above_the_limit(self):
        # The limit is only for deposits. It is never checked against the balance.
        self.assertEqual(SavingsAccount("S", "A", "90000").balance, D("90000.00"))
        self.assertEqual(CheckingAccount("C", "B", "90000").balance, D("90000.00"))

    def test_the_two_limits_work_independently(self):
        with mock.patch.object(SavingsAccount, "MAX_DEPOSIT", D("10000.00")):
            savings, checking = self.accounts()
            with self.assertRaises(DepositLimitError) as ctx:
                savings.deposit("15000")
            self.assertEqual(ctx.exception.message,
                             "Maximum deposit is PHP 10,000.00 per transaction.")
            checking.deposit("15000")
            self.assertEqual(checking.balance, D("20000.00"))
        with mock.patch.object(CheckingAccount, "MAX_DEPOSIT", D("10000.00")):
            savings, checking = self.accounts()
            savings.deposit("15000")
            self.assertEqual(savings.balance, D("20000.00"))
            with self.assertRaises(DepositLimitError):
                checking.deposit("15000")

    def test_minimum_and_bill_step_rules_still_apply(self):
        for acc in self.accounts():
            with self.subTest(acc=acc.account_type):
                with self.assertRaises(MinimumDepositError):
                    acc.deposit("50")
                with self.assertRaises(InvalidAmountError):
                    acc.deposit("250")
                with self.assertRaises(InvalidAmountError):
                    acc.deposit("0")
                acc.deposit("100")
                self.assertEqual(acc.balance, D("5100.00"))

    def test_generic_account_has_no_deposit_limit(self):
        self.assertIsNone(Account.MAX_DEPOSIT)
        account = Account("G", "Generic", "0")
        account.deposit("50000")
        self.assertEqual(account.balance, D("50000.00"))

    def test_deposit_limit_error_is_its_own_atm_error(self):
        self.assertTrue(issubclass(DepositLimitError, ATMError))
        self.assertFalse(issubclass(DepositLimitError, WithdrawalLimitError))
        self.assertEqual(DepositLimitError().message, self.LIMIT_MESSAGE)

    def test_withdrawal_limits_are_unchanged(self):
        with self.assertRaises(WithdrawalLimitError):
            SavingsAccount("S", "A", "50000").withdraw("5100")
        with self.assertRaises(WithdrawalLimitError):
            CheckingAccount("C", "B", "50000").withdraw("20100")
        self.assertEqual(CheckingAccount("C", "B", "50000").withdraw("20000").amount,
                         D("20000.00"))

    def test_saved_data_round_trip_after_limit_deposits(self):
        for acc in self.accounts("500"):
            with self.subTest(acc=acc.account_type):
                acc.deposit("20000")
                with self.assertRaises(DepositLimitError):
                    acc.deposit("20100")
                restored = type(acc).from_dict(json.loads(json.dumps(acc.to_dict())))
                self.assertEqual(restored.balance, D("20500.00"))
                self.assertEqual(len(restored.transactions), 1)

class PolymorphismTests(unittest.TestCase):
    """Goal 9: same call, different result."""

    def test_same_call_different_result(self):
        accounts = [SavingsAccount("S", "A", "20000"),
                    CheckingAccount("C", "B", "20000")]
        results = []
        for acc in accounts:           # one common interface
            try:
                acc.withdraw("10000")
                results.append("ok")
            except ATMError as e:
                results.append(type(e).__name__)
        self.assertEqual(results, ["WithdrawalLimitError", "ok"])

    def test_savings_blocks_what_checking_allows(self):
        s = SavingsAccount("S", "A", "600")
        c = CheckingAccount("C", "B", "600")
        with self.assertRaises(InsufficientFundsError):
            s.withdraw("200")
        c.withdraw("200")
        self.assertEqual(c.balance, D("400.00"))

    def test_is_a_relationship(self):
        self.assertIsInstance(SavingsAccount("S", "A", "500"), Account)
        self.assertIsInstance(CheckingAccount("C", "B"), Account)


class SerializationTests(unittest.TestCase):
    """Goal 7."""

    def test_account_round_trip_keeps_type_and_history(self):
        for cls, start in [(SavingsAccount, "5000"), (CheckingAccount, "5000")]:
            with self.subTest(cls=cls.__name__):
                a = cls("1", "Ana", start)
                a.deposit("200")
                a.withdraw("100")
                b = cls.from_dict(a.to_dict())
                self.assertIs(type(b), cls)
                self.assertEqual(b.balance, a.balance)
                self.assertEqual([t.to_dict() for t in b.transactions],
                                 [t.to_dict() for t in a.transactions])

    def test_restored_account_still_enforces_rule(self):
        a = SavingsAccount("1", "Ana", "1000")
        b = SavingsAccount.from_dict(a.to_dict())
        with self.assertRaises(InsufficientFundsError):
            b.withdraw("600")

    def test_service_round_trip(self):
        svc = ATMService.with_sample_accounts()
        svc.deposit("1001", "100")
        svc.withdraw("2001", "5000")
        # go through JSON like a Django session would
        data = json.loads(json.dumps(svc.to_dict()))
        svc2 = ATMService.from_dict(data)
        self.assertIsInstance(svc2.get_account("1001"), SavingsAccount)
        self.assertIsInstance(svc2.get_account("2001"), CheckingAccount)
        self.assertEqual(svc2.get_balance("1001"), D("15100.00"))
        self.assertEqual(svc2.get_balance("2001"), D("20000.00"))
        self.assertEqual(len(svc2.get_history("1001")), 1)
        self.assertEqual(len(svc2.get_history("2001")), 1)

    def test_unknown_type_rejected(self):
        with self.assertRaises(ATMError):
            ATMService.from_dict({"accounts": [{"account_type": "Gold"}]})


class ATMServiceTests(unittest.TestCase):
    """Goals 1 and 8."""

    def setUp(self):
        self.svc = ATMService.with_sample_accounts()

    def test_sample_accounts(self):
        self.assertEqual(len(self.svc.list_accounts()), 2)
        self.assertEqual(self.svc.get_balance("1001"), D("15000.00"))
        self.assertEqual(self.svc.get_balance("2001"), D("25000.00"))

    def test_account_number_as_int_or_str(self):
        self.assertEqual(self.svc.get_account(1001).holder_name, "Maria Santos")

    def test_missing_account(self):
        for op in (lambda: self.svc.get_account("9999"),
                   lambda: self.svc.get_balance("9999"),
                   lambda: self.svc.deposit("9999", "10"),
                   lambda: self.svc.withdraw("9999", "10"),
                   lambda: self.svc.get_history("9999"),
                   lambda: self.svc.get_account(None)):
            with self.assertRaises(ATMError) as ctx:
                op()
            self.assertEqual(ctx.exception.message, "Account not found.")

    def test_duplicate_account(self):
        with self.assertRaises(ATMError):
            self.svc.add_account(CheckingAccount("1001", "Dup"))

    def test_full_workflow(self):
        self.svc.deposit("1001", "500")
        self.svc.withdraw("1001", "1000")
        self.svc.withdraw("2001", "1000")
        self.assertEqual(self.svc.get_balance("1001"), D("14500.00"))
        self.assertEqual(self.svc.get_balance("2001"), D("24000.00"))
        with self.assertRaises(WithdrawalLimitError):
            self.svc.withdraw("2001", "20100")
        with self.assertRaises(InsufficientFundsError):
            self.svc.withdraw("1001", "14500")
        self.assertEqual(self.svc.get_balance("1001"), D("14500.00"))
        self.assertEqual(self.svc.get_balance("2001"), D("24000.00"))
        self.assertEqual([t.kind for t in self.svc.get_history("1001")],
                         ["deposit", "withdrawal"])
        self.assertEqual(len(self.svc.get_history("2001")), 1)

    def test_accounts_independent(self):
        self.svc.deposit("1001", "100")
        self.assertEqual(self.svc.get_history("2001"), [])

    def test_sample_accounts_are_fresh_each_time(self):
        self.svc.deposit("1001", "100")
        self.assertEqual(ATMService.with_sample_accounts().get_balance("1001"),
                         D("15000.00"))

class CardTests(unittest.TestCase):
    """Phase 2: PIN hashing, attempts, blocking, change PIN."""

    def setUp(self):
        self.card = Card.create("C1", "1001", "123456")

    def test_correct_pin_accepted(self):
        self.card.verify_pin("123456")  # no exception
        self.assertEqual(self.card.failed_attempts, 0)

    def test_bad_pin_format_rejected_and_not_counted(self):
        bad_pins = ["12345", "1234567", "12345a", "", "12 456", "١٢٣٤٥٦", None, 123456]
        for bad in bad_pins:
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidPinError):
                    self.card.verify_pin(bad)
        self.assertEqual(self.card.failed_attempts, 0)
        self.assertFalse(self.card.is_blocked)

    def test_create_rejects_bad_pin(self):
        with self.assertRaises(InvalidPinError):
            Card.create("C2", "1001", "1234")

    def test_wrong_pin_messages_then_block(self):
        with self.assertRaises(IncorrectPinError) as first:
            self.card.verify_pin("000000")
        self.assertEqual(first.exception.message, "Incorrect PIN. Please try again.")
        self.assertEqual(first.exception.attempts_left, 2)

        with self.assertRaises(IncorrectPinError) as second:
            self.card.verify_pin("000000")
        self.assertEqual(second.exception.message, "Incorrect PIN. Last attempt remaining.")
        self.assertEqual(second.exception.attempts_left, 1)

        with self.assertRaises(CardBlockedError):
            self.card.verify_pin("000000")
        self.assertTrue(self.card.is_blocked)

    def test_blocked_card_rejects_correct_pin(self):
        for _ in range(Card.MAX_ATTEMPTS):
            with self.assertRaises(ATMError):
                self.card.verify_pin("000000")
        with self.assertRaises(CardBlockedError):
            self.card.verify_pin("123456")

    def test_correct_pin_resets_the_counter(self):
        with self.assertRaises(IncorrectPinError):
            self.card.verify_pin("000000")
        self.card.verify_pin("123456")
        self.assertEqual(self.card.failed_attempts, 0)

    def test_pin_is_not_stored(self):
        data = self.card.to_dict()
        self.assertNotIn("pin", data)
        self.assertEqual(len(data["pin_hash"].split("$")), 2)
        # Same PIN, new card: a new random salt gives a different hash.
        other = Card.create("C2", "1001", "123456")
        self.assertNotEqual(other.to_dict()["pin_hash"], data["pin_hash"])

    def test_change_pin(self):
        self.card.change_pin("123456", "111222", "111222")
        with self.assertRaises(IncorrectPinError):
            self.card.verify_pin("123456")  # old PIN no longer works
        self.card.verify_pin("111222")      # new PIN works

    def test_change_pin_rejected_cases(self):
        cases = [
            ("123456", "111222", "111223", InvalidPinError),   # confirm differs
            ("123456", "11122", "11122", InvalidPinError),     # too short
            ("123456", "123456", "123456", InvalidPinError),   # same as current
            ("000000", "111222", "111222", IncorrectPinError),  # wrong current PIN
        ]
        for current, new, confirm, error in cases:
            with self.subTest(new=new, confirm=confirm):
                card = Card.create("C3", "1001", "123456")
                with self.assertRaises(error):
                    card.change_pin(current, new, confirm)
                card.verify_pin("123456")  # old PIN still works

    def test_typing_mistakes_cost_no_attempt(self):
        with self.assertRaises(InvalidPinError):
            self.card.change_pin("123456", "111222", "111223")
        self.assertEqual(self.card.failed_attempts, 0)

    def test_wrong_current_pin_counts_as_attempt(self):
        with self.assertRaises(IncorrectPinError):
            self.card.change_pin("000000", "111222", "111222")
        self.assertEqual(self.card.failed_attempts, 1)

    def test_round_trip_keeps_pin_attempts_and_block(self):
        with self.assertRaises(IncorrectPinError):
            self.card.verify_pin("000000")
        restored = Card.from_dict(json.loads(json.dumps(self.card.to_dict())))
        self.assertEqual(restored.failed_attempts, 1)
        restored.verify_pin("123456")

        for _ in range(Card.MAX_ATTEMPTS):
            with self.assertRaises(ATMError):
                restored.verify_pin("000000")
        blocked = Card.from_dict(restored.to_dict())
        self.assertTrue(blocked.is_blocked)

    def test_bad_saved_card_data_rejected(self):
        good = self.card.to_dict()
        bad_changes = [
            {"pin_hash": "nodollarsign"},
            {"pin_hash": "zz$zz"},
            {"pin_hash": None},
            {"failed_attempts": -1},
            {"failed_attempts": 99},
            {"failed_attempts": True},
            {"blocked": "yes"},
        ]
        for change in bad_changes:
            with self.subTest(change=change):
                with self.assertRaises(ATMError):
                    Card.from_dict({**good, **change})


class ServiceCardTests(unittest.TestCase):
    """Phase 2: ATMService works with cards."""

    def setUp(self):
        self.svc = ATMService.with_sample_accounts()

    def test_sample_cards(self):
        self.assertEqual(len(self.svc.list_cards()), 2)
        savings = self.svc.verify_pin("5000000000001001", "123456")
        checking = self.svc.verify_pin("5000000000002001", "654321")
        self.assertIsInstance(savings, SavingsAccount)
        self.assertIsInstance(checking, CheckingAccount)

    def test_unknown_card(self):
        with self.assertRaises(ATMError) as ctx:
            self.svc.verify_pin("9999", "123456")
        self.assertEqual(ctx.exception.message, "Card not found.")

    def test_card_needs_a_real_account(self):
        with self.assertRaises(ATMError):
            self.svc.add_card(Card.create("C9", "9999", "123456"))

    def test_duplicate_card(self):
        with self.assertRaises(ATMError):
            self.svc.add_card(Card.create("5000000000001001", "1001", "123456"))

    def test_wrong_pin_through_service(self):
        with self.assertRaises(IncorrectPinError):
            self.svc.verify_pin("5000000000001001", "000000")
        self.assertEqual(self.svc.get_card("5000000000001001").failed_attempts, 1)

    def test_change_pin_through_service(self):
        self.svc.change_pin("5000000000001001", "123456", "222333", "222333")
        with self.assertRaises(IncorrectPinError):
            self.svc.verify_pin("5000000000001001", "123456")
        self.svc.verify_pin("5000000000001001", "222333")

    def test_cards_survive_round_trip(self):
        for _ in range(Card.MAX_ATTEMPTS):
            with self.assertRaises(ATMError):
                self.svc.verify_pin("5000000000001001", "000000")
        self.svc.change_pin("5000000000002001", "654321", "999888", "999888")

        data = json.loads(json.dumps(self.svc.to_dict()))
        svc2 = ATMService.from_dict(data)
        self.assertTrue(svc2.get_card("5000000000001001").is_blocked)
        svc2.verify_pin("5000000000002001", "999888")

    def test_old_saved_data_without_cards_is_rejected(self):
        old = {"accounts": [a.to_dict() for a in self.svc.list_accounts()]}
        with self.assertRaises(KeyError):
            ATMService.from_dict(old)

class ReceiptTests(unittest.TestCase):
    """Phase 3: receipts built from transactions."""

    def test_savings_withdrawal_receipt(self):
        acc = SavingsAccount("1001", "Maria", "15000")
        receipt = Receipt(acc.withdraw("5000"), acc)
        self.assertEqual(receipt.bank_name, "PELEC Bank")
        self.assertEqual(receipt.location, "CTU")
        self.assertEqual(receipt.transaction_type, "Cash Withdrawal")
        self.assertEqual(receipt.amount, D("5000.00"))
        self.assertEqual(receipt.account_type, "Savings Account")
        self.assertEqual(receipt.masked_account, "****1001")
        self.assertEqual(receipt.current_balance, D("10000.00"))
        self.assertEqual(receipt.available_balance, D("9500.00"))

    def test_current_and_available_are_different_values(self):
        sav = SavingsAccount("1", "A", "5000")
        chk = CheckingAccount("2", "B", "5000")
        r_sav = Receipt(sav.deposit("1000"), sav)
        r_chk = Receipt(chk.deposit("1000"), chk)
        self.assertEqual(r_sav.current_balance, D("6000.00"))
        self.assertEqual(r_sav.available_balance, D("5500.00"))  # minus 500
        self.assertEqual(r_chk.current_balance, D("6000.00"))
        self.assertEqual(r_chk.available_balance, D("6000.00"))  # no minimum

    def test_deposit_receipt(self):
        acc = CheckingAccount("2001", "Juan", "25000")
        receipt = Receipt(acc.deposit("300"), acc)
        self.assertEqual(receipt.transaction_type, "Cash Deposit")
        self.assertEqual(receipt.amount, D("300"))
        self.assertEqual(receipt.current_balance, D("25300.00"))

    def test_available_balance_zero_at_minimum(self):
        acc = SavingsAccount("1", "A", "1000")
        receipt = Receipt(acc.withdraw("500"), acc)
        self.assertEqual(receipt.current_balance, D("500.00"))
        self.assertEqual(receipt.available_balance, D("0.00"))

    def test_rows_text(self):
        acc = SavingsAccount("1001", "Maria", "15000")
        when = datetime(2026, 11, 8, 14, 35, 7)
        receipt = Receipt(Transaction("withdrawal", "5000", "10000", when), acc)
        self.assertEqual(receipt.rows(), [
            ("Date", "08 Nov 2026"),
            ("Time", "02:35:07 PM"),
            ("Location", "CTU"),
            ("Transaction", "Cash Withdrawal"),
            ("Amount", "PHP 5,000.00"),
            ("Account", "Savings Account"),
            ("Account No.", "****1001"),
            ("Current Balance", "PHP 10,000.00"),
            ("Available Balance", "PHP 9,500.00"),
        ])

    def test_receipt_is_read_only(self):
        acc = CheckingAccount("1", "A", "5000")
        receipt = Receipt(acc.deposit("100"), acc)
        with self.assertRaises(AttributeError):
            receipt.amount = D("999")

    def test_service_make_receipt(self):
        svc = ATMService.with_sample_accounts()
        tx = svc.withdraw("1001", "1000")
        receipt = svc.make_receipt("1001", tx)
        self.assertEqual(receipt.current_balance, D("14000.00"))
        with self.assertRaises(ATMError):
            svc.make_receipt("9999", tx)

    def test_recent_receipts_newest_first_and_limited(self):
        svc = ATMService.with_sample_accounts()
        for amount in ("100", "200", "300", "400", "500", "600"):
            svc.withdraw("2001", amount)
        receipts = svc.recent_receipts("2001")
        self.assertEqual([r.amount for r in receipts],
                         [D("600.00"), D("500.00"), D("400.00"), D("300.00")])
        self.assertEqual(len(svc.recent_receipts("2001", count=2)), 2)

    def test_old_receipt_keeps_its_own_balances(self):
        svc = ATMService.with_sample_accounts()
        svc.withdraw("1001", "1000")
        svc.withdraw("1001", "2000")
        newest, oldest = svc.recent_receipts("1001")
        self.assertEqual(newest.current_balance, D("12000.00"))
        self.assertEqual(oldest.current_balance, D("14000.00"))
        self.assertEqual(oldest.available_balance, D("13500.00"))

    def test_recent_receipts_empty_and_unknown_account(self):
        svc = ATMService.with_sample_accounts()
        self.assertEqual(svc.recent_receipts("1001"), [])
        with self.assertRaises(ATMError):
            svc.recent_receipts("9999")

    def test_receipts_work_after_session_round_trip(self):
        svc = ATMService.with_sample_accounts()
        svc.withdraw("1001", "1000")
        svc2 = ATMService.from_dict(json.loads(json.dumps(svc.to_dict())))
        receipt = svc2.recent_receipts("1001")[0]
        self.assertEqual(receipt.current_balance, D("14000.00"))
        self.assertEqual(receipt.available_balance, D("13500.00"))

def new_request(cookie=None):
    """Fake request. cookie=None means first visit."""
    return SimpleNamespace(session=SessionStore(cookie))

def end_request(request):
    """Do what Django does at the end of a request: make the cookie value."""
    request.session.save()
    return request.session.session_key



class SessionStateTests(unittest.TestCase):
    """Phase 5, step 1: save and restore ATMService in the session."""

    def test_first_visit_creates_samples(self):
        req = new_request()
        service = load_service(req)
        self.assertEqual(service.get_balance("1001"), D("15000.00"))
        self.assertIsInstance(req.session[SESSION_KEY], dict)

    def test_state_survives_between_requests(self):
        # Request 1: change state and save it.
        req1 = new_request()
        service = load_service(req1)
        service.deposit("1001", "100")
        service.withdraw("2001", "5000")
        save_service(req1, service)
        cookie = end_request(req1)

        # Request 2: same browser sends the cookie back.
        req2 = new_request(cookie)
        service2 = load_service(req2)
        self.assertEqual(service2.get_balance("1001"), D("15100.00"))
        self.assertEqual(service2.get_balance("2001"), D("20000.00"))
        self.assertEqual(len(service2.get_history("1001")), 1)
        self.assertIsInstance(service2.get_account("2001"), CheckingAccount)

    def test_session_holds_plain_data_only(self):
        req = new_request()
        service = load_service(req)
        service.deposit("1001", "100")
        save_service(req, service)
        data = req.session[SESSION_KEY]
        json.dumps(data)  # raises TypeError if Decimal or objects are inside
        self.assertEqual(data["accounts"][0]["balance"], "15100.00")

    def test_bad_saved_data_resets_safely(self):
        bad_values = [
            {},
            "text",
            {"accounts": None},
            {"accounts": [{"account_type": "Gold"}]},
            {"accounts": [{"account_type": "Savings Account"}]},
            {"accounts": []},  # old format: no "cards" key

        ]
        for bad in bad_values:
            with self.subTest(bad=bad):
                req = new_request()
                req.session[SESSION_KEY] = bad
                service = load_service(req)
                self.assertEqual(service.get_balance("1001"), D("15000.00"))
                self.assertEqual(
                    req.session[SESSION_KEY]["accounts"][0]["account_number"], "1001"
                )

    def test_too_large_is_refused_and_old_data_kept(self):
        req = new_request()
        service = load_service(req)
        before = req.session[SESSION_KEY]
        service.deposit("1001", "100")
        # Pretend the cookie limit is tiny so the check fires.
        with mock.patch("atm_app.session_state.MAX_SESSION_CHARS", 100):
            with self.assertRaises(ATMError):
                save_service(req, service)
        self.assertEqual(req.session[SESSION_KEY], before)

    def test_programming_errors_are_not_hidden(self):
        # No .session on the request is a bug, not bad data. It must crash.
        with self.assertRaises(AttributeError):
            load_service(SimpleNamespace())

class HistoryCapTests(unittest.TestCase):
    """Phase 5: saved history keeps only the newest transactions."""

    def test_saved_history_keeps_last_ten(self):
        acc = CheckingAccount("1", "Ana", "0")
        for i in range(1, 16):
            acc.deposit(str(i * 100))
        saved = acc.to_dict()["transactions"]
        self.assertEqual(len(saved), Account.MAX_SAVED_TRANSACTIONS)
        self.assertEqual(saved[0]["amount"], "600.00")    # oldest one kept
        self.assertEqual(saved[-1]["amount"], "1500.00")  # newest
        self.assertEqual(len(acc.transactions), 15)     # memory untouched

    def test_balance_stays_exact_after_trim(self):
        acc = CheckingAccount("1", "Ana", "0")
        for i in range(1, 16):
            acc.deposit(str(i * 100))
        restored = CheckingAccount.from_dict(acc.to_dict())
        self.assertEqual(restored.balance, D("12000.00"))
        self.assertEqual(len(restored.transactions), 10)

if __name__ == "__main__":
    unittest.main()
