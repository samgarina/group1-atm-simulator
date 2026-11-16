# OOP Concept Mapping

This document maps core Object-Oriented Programming (OOP) concepts and architectural patterns to their specific locations within the ATM Simulator codebase.

| OOP Concept / Architecture | File | Class | Method / Property | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Encapsulation** | `atm_app/atm_classes.py` | `Account` | `balance` | The actual balance is protected (`_balance`). It can only be read externally via the `@property def balance(self)` method, and modified internally through controlled `deposit()` or `withdraw()` methods. |
| **Inheritance** | `atm_app/atm_classes.py` | `SavingsAccount`, `CheckingAccount` | `check_withdrawal()` | `SavingsAccount` and `CheckingAccount` inherit from the parent `Account` class, inheriting base properties while overriding specific rule checks. |
| **Polymorphism** | `atm_app/atm_classes.py` | `SavingsAccount`, `CheckingAccount` | `withdraw(amount)` | Calling `withdraw()` triggers different rules depending on the object type (checking maintaining balances for Savings, or applying higher limits for Checking). |
| **Exception Handling** | `atm_app/exceptions.py` | `ATMError` and Subclasses | `__init__()` | Custom domain exceptions (e.g., `InsufficientFundsError`, `InvalidPinError`) inherit from a base `ATMError` to handle logic violations cleanly without crashing the app. |
| **Separation of Concerns** (Views to Classes) | `atm_app/views.py`, `atm_app/atm_flow.py` | `ATMFlow`, `ATMService` | `submit_amount()`, `_confirm()` | Django views do not contain money logic. Views pass user input to `ATMFlow` (screen states), which delegates transactions to `ATMService`, which finally calls methods on the `Account` objects. |

## Polymorphism Example in Action

Polymorphism allows the system to treat different account types uniformly while they execute their own specialized behaviors. 

In `atm_app/atm_classes.py`, the `ATMService` class routes a withdrawal without needing to check `if type == "Savings"`:

```python
    def withdraw(self, account_number, amount):
        # The service does not know the account type. Each account applies its own rule.
        return self.get_account(account_number).withdraw(amount)