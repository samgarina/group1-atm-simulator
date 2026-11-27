## 1. Accounts (atm_classes.py)
| Class | Parent | Members |
|---|---|---|
| Account | none | read-only properties: account_number, holder_name, masked_number, balance, transactions, available_balance. Methods: deposit(amount), withdraw(amount), check_deposit(amount), check_withdrawal(amount), to_dict(), from_dict(data) |
| SavingsAccount | Account | overrides check_withdrawal() |
| CheckingAccount | Account | overrides check_withdrawal() |

deposit() and withdraw() return a Transaction. check_deposit() and
check_withdrawal() return the clean amount and change nothing.
withdraw() calls self.check_withdrawal(), so each account type applies its
own rule (polymorphism).

Rules for all accounts: minimum deposit PHP 100, minimum withdrawal PHP 100,
amounts in multiples of PHP 100, a withdrawal cannot be above the balance.
Savings: balance must stay at or above PHP 500, maximum PHP 5,000 per withdrawal.
Checking: maximum PHP 20,000 per withdrawal.
to_dict() saves only the newest 10 transactions.

## 2. Exceptions (exceptions.py)
All inherit from ATMError (verify in exceptions.py). Each has a .message.
| Name | Raised when |
|---|---|
| ATMError | parent of all ATM errors |
| InvalidAmountError | not a number, nan, inf, more than 2 decimals, zero, negative, not a multiple of 100 |
| MinimumDepositError | deposit below PHP 100 |
| MinimumWithdrawalError | withdrawal below PHP 100 |
| InsufficientFundsError | amount above the balance, or savings would fall below PHP 500 |
| WithdrawalLimitError | amount above the per-withdrawal limit |
| InvalidPinError | PIN is not 6 digits, PINs do not match, or new PIN equals the old PIN |
| IncorrectPinError | wrong PIN. Has attempts_left. |
| CardBlockedError | card blocked after 3 wrong PINs |

## 3. Amount checks (atm_classes.py)
_to_money(value) returns a Decimal with 2 decimal places or raises
InvalidAmountError. format_money(value) returns text such as "PHP 1,000.00".
Zero and negative amounts are rejected by Account._validate_amount().

## 4. Transaction (atm_classes.py)
Fields (read-only): kind ("deposit" or "withdrawal"), amount, balance_after
(Decimal), timestamp. Methods: to_dict(), from_dict(data).

## 5. Card and Receipt (atm_classes.py)
Card.create(card_number, account_number, pin). PIN is 6 digits and is stored
hashed, never in plain text. Methods: verify_pin(pin), change_pin(current_pin,
new_pin, confirm_pin), to_dict(), from_dict(data). Properties: card_number,
account_number, failed_attempts, attempts_left, is_blocked. 3 wrong PINs block the card.
Receipt(transaction, account). Properties: bank_name, location, timestamp,
transaction_type, amount, account_type, masked_account, current_balance,
available_balance. rows() returns (label, value) pairs.

## 6. ATMService (atm_classes.py)
ATMService(accounts=None, cards=None). ATMService.with_sample_accounts() makes
the two demo accounts and cards.
| Method | Parameters | Returns |
|---|---|---|
| add_account, get_account, list_accounts | account or account_number | account or list |
| add_card, get_card, list_cards | card or card_number | card or list |
| verify_pin | card_number, pin | the account |
| change_pin | card_number, current_pin, new_pin, confirm_pin | none |
| deposit, withdraw | account_number, amount | Transaction |
| get_balance | account_number | Decimal |
| get_history | account_number | list of Transaction |
| make_receipt | account_number, transaction | Receipt |
| recent_receipts | account_number, count=4 | list of Receipt, newest first |
| to_dict, from_dict | none, data | dict, ATMService |
Failure rule: on any error, the balance and the history stay unchanged.

## 7. Screen flow (atm_flow.py)
ATMFlow(service). Input methods: insert_card(card_number), submit_pin(pin),
choose(slot), submit_amount(value), submit_change_pin(current_pin, new_pin,
confirm_pin), cancel(), eject(), finish(). They return nothing and do not
raise ATMError. Errors become a message on the next screen.
Read the screen with screen(). Also: receipt_paper(), cash_amount(), to_dict(),
ATMFlow.from_dict(service, data). Properties: screen_name, card_inserted,
authenticated, card_number.
Screen: name, title, message, options, input_mode ("none", "pin", "amount",
"change_pin"), prompts, rows; left_options() and right_options() give 4
items each (None = disabled button). Slots: L1 to L4, R1 to R4.
Screen names: welcome, pin, menu, balance, withdraw_amount, deposit_amount,
confirm, collect, additional, mini_statement, receipt_view, account_info,
change_pin.

## 8. Session (session_state.py)
save_service(request, service), load_service(request): the ATMService, stored
under SESSION_KEY. save_flow(request, flow), load_flow(request, service): the
screen state, stored under FLOW_KEY and RUN_KEY. A saved screen from an
earlier server run is dropped. Bad saved data starts fresh. Balances are kept.
Saved data is limited to 3500 characters (MAX_SESSION_CHARS).

## 9. URL names (urls.py, owner: Garina)
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

## 10. Template context (views.py to index.html)
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

## 11. Change rule
Only the file owner edits a file. An interface change needs a PR that
updates this file, a note in the group chat, and approval from the
affected member.
