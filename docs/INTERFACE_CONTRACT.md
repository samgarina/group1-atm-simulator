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

## 4. Transaction (atm_classes.py.py, owner: Senilong)
Fields: <type, amount, balance after, time>. Method: to_dict().

## 5. ATMService (atm_classes.py, owner: Senilong)
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

## 8. URL names (urls.py, owner: Garina)
All names use the prefix atm_app: in templates, for example {% url 'atm_app:choose' %}.
urls.py must keep app_name = "atm_app".

| URL name | Path | View | Method | Form fields | Scope |
|---|---|---|---|---|---|
| home | "" | home | GET | none | Core |
| insert_card | insert-card/ | insert_card | POST | card_number | Core (selects the account) |
| choose | choose/ | choose | POST | slot | Core |
| submit_amount | amount/ | submit_amount | POST | amount | Core |
| cancel | cancel/ | cancel | POST | none | Core |
| reset | reset/ | reset | POST | none | Core |
| submit_pin | pin/ | submit_pin | POST | pin | Optional (team decides) |
| change_pin | change-pin/ | change_pin | POST | current_pin, new_pin, confirm_pin | Optional (team decides) |
| eject | eject/ | eject | not confirmed | not confirmed | Optional (team decides) |
| collect | collect/ | collect | POST | none | Optional (team decides) |

Garina creates these routes in urls.py and views.py.
Mahinay uses the names in index.html with {% url %}.

## 9. Template context (views.py to index.html)
The view passes one dictionary to render(request, "atm_app/index.html", context).

| Key | Contains | Used for |
|---|---|---|
| messages | Django messages | success and error text |
| screen | name, title, message, rows, input_mode, prompts | what the monitor shows and which input form appears |
| left, right | lists of items with slot and option (label, sub) | side-button labels |
| wallet | list of cards: card_number, last_four, owner, account_type, blocked | welcome screen card list |
| card_info | last_four, owner, account_type | card shown on the collect screen |
| receipt | bank_name, rows | printed receipt |
| cash_text | text | dispensed cash popup |
| demo_help | list of rows: owner, account_type, last_four, pin | demo account help table |

Garina passes these keys (PR Gr5).
Mahinay displays them in index.html (PR M6).

## 10. Change rule
Only the file owner edits a file. An interface change needs a PR that
updates this file, a note in the group chat, and approval from the
affected member.