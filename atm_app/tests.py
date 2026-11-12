import unittest
from decimal import Decimal
from .exceptions import (
    ATMError,
    InvalidAmountError,
    InsufficientFundsError,
    WithdrawalLimitError,
)
from .atm_classes import (
    Account,
    Transaction,
    _to_money,
)

D = Decimal


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


if __name__ == "__main__":
    unittest.main()