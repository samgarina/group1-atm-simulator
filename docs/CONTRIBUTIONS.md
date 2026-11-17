# Member Contribution Record

**Course:** P ELEC 1 - Object-Oriented Programming (Python and Django)
**Project:** ATM Simulator (Option C)
**Group No.:** 1 **Course and Section:** BSIT II-A

This file records who was responsible for what, which features each member completed, and which pull request delivered each file. Every file in the project has exactly one owner, so no two members edited the same file.

## Members and roles

| Member | Main role |
|---|---|
| Cardente | OOP core: account classes, polymorphism, class diagram, OOP mapping |
| Garciano | Custom exceptions, validation, web and integration tests, test report |
| Senilong | ATM flow logic, session management, interface contract, contribution record |
| Garina | Django views, URL routing, settings, repository setup, README |
| Mahinay | Frontend: HTML template, CSS, JavaScript |

## Responsibilities and completed features

### Cardente
- Built the account classes in `atm_app/atm_classes.py`: the base `Account` with a private balance and a read-only `balance` property.
- Built `SavingsAccount` (keeps a minimum balance) and `CheckingAccount` (per-withdrawal limit). Both override `withdraw()`, which shows inheritance and polymorphism.
- Built the transaction, card and receipt classes in the same file.
- Wrote the account tests in `atm_app/tests.py`.
- Wrote `docs/UML.md` (class diagram) and `docs/OOP_MAPPING.md` (each OOP concept mapped to file, class and method).

### Garciano
- Built the custom exception classes in `atm_app/exceptions.py`. Each has a readable message that is shown to the user.
- Wrote the web and integration tests in `atm_app/test_web.py`: views, messages, invalid input, overdraft and the full ATM flow.
- Wrote `docs/TEST_REPORT.md` with the six documented test cases (normal, boundary, invalid, business rule, polymorphism, exception handling).

### Senilong
- Built `atm_app/session_state.py`: load, save and reset of accounts and cards through the signed-cookie session.
- Built `atm_app/atm_flow.py` (`ATMFlow`): the layer that takes form input, calls the OOP classes, saves the session and returns a result or an error message.
- Wrote the flow and session tests in `atm_app/test_flow.py`.
- Wrote `docs/INTERFACE_CONTRACT.md` (signatures, exceptions, session keys, URL names, template context keys) and this contribution record.

### Garina
- Set up the repository: `.gitignore` (virtual environments, cache files, `db.sqlite3`).
- Configured `atm_project/settings.py`: registered `atm_app`, signed-cookie sessions, time zone, messages.
- Built `atm_app/views.py` and `atm_app/urls.py` (and `atm_project/urls.py` where changed): named routes and views that call `ATMFlow` and show Django messages.
- Wrote `README.md`: title, members, Python version, setup, run steps, workflow and known limitations.

### Mahinay
- Built the ATM machine page in `atm_app/templates/atm_app/index.html`: monitor, side buttons, keypad area, forms with CSRF tokens, and receipt display.
- Styled the ATM in `atm_app/static/atm_app/css/style.css`.
- Added keypad and keyboard interaction in `atm_app/static/atm_app/js/script.js`. JavaScript only handles input. All rules stay in Python.

## File ownership

| File | Owner |
|---|---|
| `atm_app/exceptions.py` | Garciano |
| `atm_app/atm_classes.py` | Cardente |
| `atm_app/session_state.py` | Senilong |
| `atm_app/atm_flow.py` | Senilong |
| `atm_app/views.py`, `atm_app/urls.py`, `atm_project/urls.py` | Garina |
| `atm_project/settings.py`, `.gitignore`, `README.md` | Garina |
| `atm_app/templates/atm_app/index.html` | Mahinay |
| `atm_app/static/atm_app/css/style.css` | Mahinay |
| `atm_app/static/atm_app/js/script.js` | Mahinay |
| `atm_app/tests.py` | Cardente |
| `atm_app/test_flow.py` | Senilong |
| `atm_app/test_web.py` | Garciano |
| `docs/UML.md`, `docs/OOP_MAPPING.md` | Cardente |
| `docs/TEST_REPORT.md` | Garciano |
| `docs/INTERFACE_CONTRACT.md`, `docs/CONTRIBUTIONS.md` | Senilong |

Not changed by the group (Django starter files): `models.py`, `admin.py`, `apps.py`, `migrations/`, `asgi.py`, `wsgi.py`.

## Pull request record

Fill in the PR number and merge date after each PR is merged.

| # | Member | Branch | Delivered | PR | Merged |
|---|---|---|---|---|---|
| 1 | Garciano | `feature/garciano-custom-exceptions` | `exceptions.py` | # | |
| 2 | Cardente | `feature/cardente-account-classes` | `atm_classes.py` | # | |
| 3 | Senilong | `docs/senilong-interface-contract` | `INTERFACE_CONTRACT.md` | # | |
| 4 | Senilong | `feature/senilong-session-state` | `session_state.py` | # | |
| 5 | Senilong | `feature/senilong-atm-flow` | `atm_flow.py` | # | |
| 6 | Garina | `chore/garina-repo-setup` | `.gitignore`, `settings.py` | # | |
| 7 | Garina | `feature/garina-views-and-routes` | `views.py`, `urls.py` | # | |
| 8 | Mahinay | `feature/mahinay-atm-template` | `index.html` | # | |
| 9 | Mahinay | `style/mahinay-atm-styles` | `style.css` | # | |
| 10 | Mahinay | `feature/mahinay-keypad-script` | `script.js` | # | |
| 11 | Cardente | `test/cardente-account-tests` | `tests.py` | # | |
| 12 | Senilong | `test/senilong-flow-tests` | `test_flow.py` | # | |
| 13 | Garciano | `test/garciano-web-tests` | `test_web.py` | # | |
| 14 | Cardente | `docs/cardente-uml-diagram` | `UML.md` | # | |
| 15 | Cardente | `docs/cardente-oop-mapping` | `OOP_MAPPING.md` | # | |
| 16 | Garciano | `docs/garciano-test-report` | `TEST_REPORT.md` | # | |
| 17 | Garina | `docs/garina-readme` | `README.md` | # | |
| 18 | Senilong | `docs/senilong-contribution-record` | `CONTRIBUTIONS.md` | # | |

## Review pairs

Each PR was reviewed by the member who uses that code, never by the author. Examples: Senilong reviewed Cardente's classes, Garina reviewed Senilong's flow, Garciano reviewed Cardente's tests and documents.

## Team work

- All members took part in the group manual test session and the code freeze check.
- All members can explain their own files, the parent and child class roles, why `withdraw()` is overridden, and how one form submission travels from the browser through the Django view to an OOP method.
- Each member is ready to make a live change (a rule, a validation or an overridden method) in their own files during the individual defense.