# BBko ATM Simulator

A fictional ATM that runs in your web browser. It is a school project for **P ELEC 1 – Object-Oriented Programming (Python and Django)**, Option C: ATM Simulator.

All names, cards, PINs and money are **fictional**. Nothing connects to a real bank.

## Project overview

The ATM screen, side buttons, keypad, card slot, cash dispenser and receipt printer are drawn in the browser. All the banking rules (balances, limits, PIN checks) are written as **Python classes**. Django only connects the web pages to those classes.

There is **no database**. The accounts live in the Django session (a signed cookie), so the data belongs to one browser. Use the **Reset demo data** button on the page to start again with the sample accounts. Restarting the server also sends the ATM back to the welcome screen.

## Technologies

- Python (the `.python-version` file says `3.14`)
- Django 6.1.3 (from `requirements.txt`)
- HTML, CSS and JavaScript (JavaScript only handles the keypad and screen effects; it does not hold any banking rules)

## Key ATM features

- Insert a sample card and enter a 6-digit PIN (3 wrong tries block the card)
- Balance inquiry
- Cash withdrawal
- Cash deposit (under Additional Services)
- Change PIN
- Account information
- Mini statement (newest transactions) and receipts
- Two account types with different rules: **Savings** and **Checking**

The sample cards and their starting PINs are shown in the on-screen demo help panel. They are defined in `ATMService.SAMPLE_CARDS` in `atm_app/atm_classes.py`.

## Important ATM rules

| Rule | Savings Account | Checking Account |
|---|---|---|
| Minimum deposit | PHP 100.00 | PHP 100.00 |
| **Maximum deposit per transaction** | **PHP 20,000.00** | **PHP 20,000.00** |
| Deposits and withdrawals in multiples of | PHP 100 | PHP 100 |
| Minimum withdrawal | PHP 100.00 | PHP 100.00 |
| Maximum withdrawal per transaction | PHP 5,000.00 | PHP 20,000.00 |
| Minimum balance to keep | PHP 500.00 | PHP 0.00 |

About the deposit limit:

- PHP 20,000.00 exactly is accepted. PHP 20,100.00 and above is rejected with: *"Maximum deposit is PHP 20,000.00 per transaction."*
- The limit is for **one deposit**. You can make many deposits. The total balance has no limit.
- Each account class (`SavingsAccount`, `CheckingAccount`) has its own `MAX_DEPOSIT` value.
- A rejected deposit never reaches the confirm screen and never changes the balance or history.
- A deposit or a withdrawal ends the session: take the card and receipt to start again.

## Project folder structure

```
manage.py
requirements.txt
.python-version
atm_project/            Django project settings and main URLs
    settings.py
    urls.py
    asgi.py
    wsgi.py
atm_app/                The ATM app
    atm_classes.py      OOP classes: Transaction, Account, SavingsAccount, CheckingAccount,
                        Receipt, Card, ATMService
    exceptions.py       Custom errors (ATMError and its children, such as DepositLimitError)
    atm_flow.py         ATMFlow: which screen is shown, and what each button or amount does
    session_state.py    Saves and loads the ATM state in the Django session
    views.py            Django views (pass input to the classes, show the result)
    urls.py             URL routes of the app
    templates/atm_app/  HTML templates (index.html and small partials)
    static/atm_app/     css/style.css, js/script.js, images/
    tests.py            Tests for the account classes, service, cards, receipts, session
    test_flow.py        Tests for the ATM screens and flow (no browser needed)
    test_web.py         Tests that use the Django test client
docs/
    CONTRIBUTIONS.md    Member contribution record
    INTERFACE_CONTRACT.md
    OOP_MAPPING.md      Where each OOP concept is used
```

## Installation and setup

1. Install Python and open a terminal in the project folder (the one with `manage.py`).
2. Create and activate a virtual environment (the `.gitignore` already ignores `.venv/`):

   ```
   python -m venv .venv
   ```

   Windows: `.venv\Scripts\activate`  
   macOS / Linux: `source .venv/bin/activate`

3. Install the requirements:

   ```
   pip install -r requirements.txt
   ```

## How to run the application

```
python manage.py runserver
```

Open <http://127.0.0.1:8000/> in your browser.

No database setup and no `migrate` step is needed, because the project does not use a database.

Optional settings (environment variables): `DJANGO_DEBUG` (default `True` when running locally) and `DJANGO_SECRET_KEY` (only required when debug mode is off). Do not put real secret values in the code or in this file.

## How to run the tests

```
python manage.py test
```

To run one test file or one test class:

```
python manage.py test atm_app.test_flow
python manage.py test atm_app.tests.DepositLimitTests
```

## Known limitations

- Data is kept only in the browser session and is not saved permanently.
- The session cookie keeps only the newest 10 transactions of each account.
- Fictional data only. Do not enter real card, PIN or bank information.
