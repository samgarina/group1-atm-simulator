# Interface Contract

Purpose: every member codes against these names. If you change a name,
a parameter or a return value, update this file in your PR and tell the team.

## 1. Accounts (atm_classes.py, owner: Cardente)
| Class | Parent | Methods | Raises |
|---|---|---|---|
| Account | none | deposit(amount), withdraw(amount), to_dict(), from_dict(data) | <exceptions> |
| SavingsAccount | Account | withdraw(amount) overridden | <exceptions> |
| CheckingAccount | Account | withdraw(amount) overridden | <exceptions> |

Read-only property: balance. Other properties: <copy from code>.
Savings rule: <rule and value>. Checking rule: <rule and value>.

## 2. Exceptions (exceptions.py, owner: Garciano)
| Name | Raised when | Message example |
|---|---|---|
| <base exception> | parent of all ATM errors | |
| <invalid amount> | blank, text, nan, inf, zero, negative | |
| <insufficient funds> | overdraft | |
| <limit exceeded> | over the account limit | |

## 3. Amount parsing (atm_flow.py, owner: Senilong)
parse_amount(raw) returns a number and raises <invalid amount>.
It checks the format only. Zero, negative and overdraft are checked by Account.

## 4. Transaction (atm_logic.py, owner: Senilong)
Fields: <type, amount, balance after, time>. Method: to_dict().

## 5. ATMService (atm_logic.py, owner: Senilong)
| Method | Parameters | Returns | Raises |
|---|---|---|---|
| deposit | account, amount | Transaction | <exceptions> |
| withdraw | account, amount | Transaction | <exceptions> |
| <balance inquiry> | account | <return> | |
Failure rule: on any error, the balance and the history stay unchanged.

## 6. Flow functions (atm_flow.py, owner: Senilong)
| Function | Parameters | Returns |
|---|---|---|
| <deposit flow> | session, raw amount | <result or error message> |
| <withdraw flow> | session, raw amount | <result or error message> |

## 7. Session (session_state.py, owner: Senilong)
Functions: <load>, <save>, <reset>.
Session keys: <names>. Stored data comes from to_dict().