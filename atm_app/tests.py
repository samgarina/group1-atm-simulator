import unittest
from decimal import Decimal
from .exceptions import (
    ATMError,
    InvalidAmountError,
    InsufficientFundsError,
    MinimumDepositError,
    MinimumWithdrawalError,
    WithdrawalLimitError,
)
from .atm_classes import (
    ATMService,
    Account,
    CheckingAccount,
    SavingsAccount,
    Transaction,
    _to_money,
)

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


class AccountBasicsTests(unittest.TestCase):
    """Goals 3, 4, 5 on the parent class."""

    def setUp(self):
        # Initializes with account number, owner, and starting balance
        self.acc = Account("001", "Ana", "1000")

    def test_balances_and_history(self):
        self.acc.deposit("300")
        self.acc.withdraw("100")
        self.assertEqual(self.acc.balance, D("1200.00"))
        kinds = [t.kind for t in self.acc.transactions]
        self.assertEqual(kinds, ["deposit", "withdrawal"])
        self.assertEqual(
            [t.balance_after for t in self.acc.transactions],
            [D("1300.00"), D("1200.00")],
        )

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
        # Checks that attempting to directly modify the balance throws an AttributeError
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
        acc = CheckingAccount("C", "B", "0")
        acc.deposit("50000")
        self.assertEqual(acc.balance, D("50000.00"))

    def test_check_deposit_changes_nothing(self):
        acc = CheckingAccount("C", "B", "5000")
        self.assertEqual(acc.check_deposit("300"), D("300.00"))
        self.assertEqual(acc.balance, D("5000.00"))
        self.assertEqual(acc.transactions, [])
        with self.assertRaises(MinimumDepositError):
            acc.check_deposit("99")


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
        self.assertEqual(accounts[0].balance, D("20000.00"))
        self.assertEqual(accounts[1].balance, D("10000.00"))

    def test_savings_blocks_what_checking_allows(self):
        s = SavingsAccount("S", "A", "600")
        c = CheckingAccount("C", "B", "600")
        with self.assertRaises(InsufficientFundsError):
            s.withdraw("200")
        c.withdraw("200")
        self.assertEqual(s.balance, D("600.00"))
        self.assertEqual(c.balance, D("400.00"))

    def test_is_a_relationship(self):
        savings = SavingsAccount("S", "A", "500")
        checking = CheckingAccount("C", "B")
        self.assertIsInstance(savings, Account)
        self.assertIsInstance(checking, Account)
        self.assertIsInstance(savings, SavingsAccount)
        self.assertIsInstance(checking, CheckingAccount)


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
                self.assertEqual(
                    [t.to_dict() for t in b.transactions],
                    [t.to_dict() for t in a.transactions],
                )
                c = Account.from_dict(a.to_dict())
                self.assertIs(type(c), cls)
                self.assertEqual(c.balance, a.balance)

    def test_restored_account_still_enforces_rule(self):
        a = SavingsAccount("1", "Ana", "1000")
        b = SavingsAccount.from_dict(a.to_dict())
        with self.assertRaises(InsufficientFundsError):
            b.withdraw("600")

    def test_unknown_type_rejected(self):
        with self.assertRaises(ATMError):
            Account.from_dict({"account_type": "Gold"})
        with self.assertRaises(ATMError):
            ATMService.from_dict({"accounts": [{"account_type": "Gold"}]})


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
        self.assertEqual(len(acc.transactions), 15)       # memory untouched

    def test_balance_stays_exact_after_trim(self):
        acc = CheckingAccount("1", "Ana", "0")
        for i in range(1, 16):
            acc.deposit(str(i * 100))
        restored = CheckingAccount.from_dict(acc.to_dict())
        self.assertEqual(restored.balance, D("12000.00"))
        self.assertEqual(len(restored.transactions), 10)


if __name__ == "__main__":
    unittest.main()