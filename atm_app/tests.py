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
    Account,
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


if __name__ == "__main__":
    unittest.main()