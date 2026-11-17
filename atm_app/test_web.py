import re
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.test import Client, SimpleTestCase
from django.urls import reverse

from .session_state import MAX_SESSION_CHARS

D = Decimal

SAVINGS_CARD = "5000000000001001"
CHECKING_CARD = "5000000000002001"
SAVINGS_PIN = "123456"
CHECKING_PIN = "654321"

POST_ROUTES = (
    "insert_card", "submit_pin", "choose", "submit_amount",
    "change_pin", "cancel", "eject", "collect", "reset",
)

INVALID = "Invalid amount. Enter a number greater than zero."
POSITIVE = "Amount must be greater than zero."


class WebFlowTests(SimpleTestCase):
    """Browser-style tests. The test client sends real requests through
    project urls, app urls, view, session and template. No database is used.
    Each test gets a fresh client, so it starts as a new browser session.
    """

    # --- helpers -------------------------------------------------------

    def go(self, name, data=None, client=None):
        """POST to a route, then follow the redirect to the home page."""
        client = client or self.client
        return client.post(reverse(f"atm_app:{name}"), data or {}, follow=True)

    def home(self, client=None):
        return (client or self.client).get(reverse("atm_app:home"))

    def press(self, slot, client=None):
        """Press a side button (L1...L4, R1...R4)."""
        return self.go("choose", {"slot": slot}, client)

    def login(self, card=SAVINGS_CARD, pin=SAVINGS_PIN, client=None):
        self.go("insert_card", {"card_number": card}, client)
        return self.go("submit_pin", {"pin": pin}, client)

    def withdraw(self, amount, client=None):
        """Menu to the collect screen. The card, cash and receipt come out."""
        self.press("L2", client)
        self.go("submit_amount", {"amount": amount}, client)
        return self.press("L4", client)  # Yes

    def deposit(self, amount, card=SAVINGS_CARD, pin=SAVINGS_PIN, client=None):
        """A deposit ends the session. Take everything and log in again."""
        self.press("R2", client)
        self.press("L1", client)
        self.go("submit_amount", {"amount": amount}, client)
        self.press("L4", client)         # Yes
        self.go("collect", client=client)
        return self.login(card, pin, client)

    def balance_text(self, client=None):
        """Read the current balance from the Balance Inquiry screen. Start on the menu."""
        response = self.press("L1", client)
        text = dict(response.context["screen"].rows)["Current Balance"]
        self.press("R4", client)         # No, back to the menu
        return text

    def screen_name(self, response):
        return response.context["screen"].name

    def enabled(self, response):
        context = response.context
        return [item["slot"] for item in context["left"] + context["right"] if item["enabled"]]

    def check_eight_buttons(self, response):
        self.assertContains(response, 'name="slot"', count=8)
        self.assertEqual(len(response.context["left"]), 4)
        self.assertEqual(len(response.context["right"]), 4)

    # --- welcome and layout --------------------------------------------

    def test_home_loads(self):
        response = self.home()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "atm_app/index.html")
        self.assertEqual(self.screen_name(response), "welcome")
        self.assertContains(response, "Welcome to PELEC Bank.")
        self.assertContains(response, "Please insert your ATM card.")
        self.assertContains(response, "Maria Santos")
        self.assertContains(response, "Juan Dela Cruz")

    def test_eight_side_buttons_on_every_screen(self):
        self.check_eight_buttons(self.home())
        self.go("insert_card", {"card_number": SAVINGS_CARD})
        self.check_eight_buttons(self.home())                       # pin
        self.check_eight_buttons(self.go("submit_pin", {"pin": SAVINGS_PIN}))  # menu
        self.check_eight_buttons(self.press("L1"))                  # balance
        self.check_eight_buttons(self.press("L4"))                  # withdraw amount
        self.check_eight_buttons(self.go("submit_amount", {"amount": "500"}))  # confirm
        self.check_eight_buttons(self.press("R4"))                  # menu
        self.check_eight_buttons(self.press("R2"))                  # additional
        self.check_eight_buttons(self.press("L3"))                  # account info

    def test_enabled_buttons_follow_the_screen(self):
        self.assertEqual(self.enabled(self.home()), [])
        response = self.login()
        self.assertEqual(self.enabled(response), ["L1", "L2", "R1", "R2", "R4"])
        self.press("L2")
        response = self.go("submit_amount", {"amount": "500"})
        self.assertEqual(self.screen_name(response), "confirm")
        self.assertEqual(self.enabled(response), ["L4", "R4"])

    def test_empty_slots_are_disabled_in_html(self):
        response = self.login()
        html = response.content.decode()
        self.assertRegex(html, r'value="L3"[^>]*disabled')
        self.assertRegex(html, r'value="R3"[^>]*disabled')
        self.assertNotRegex(html, r'value="L1"[^>]*disabled')
        self.assertNotRegex(html, r'value="R4"[^>]*disabled')

    # --- card and PIN ---------------------------------------------------

    def test_unknown_card(self):
        response = self.go("insert_card", {"card_number": "9999"})
        self.assertEqual(self.screen_name(response), "welcome")
        self.assertContains(response, "Card not found.")

    def test_card_goes_to_pin_screen(self):
        response = self.go("insert_card", {"card_number": SAVINGS_CARD})
        self.assertEqual(self.screen_name(response), "pin")
        self.assertContains(response, "Please enter your six-digit PIN.")
        self.assertTrue(response.context["card_inserted"])

    def test_wrong_pin_attempts_are_saved_and_card_blocks(self):
        self.go("insert_card", {"card_number": SAVINGS_CARD})

        response = self.go("submit_pin", {"pin": "000000"})
        self.assertEqual(self.screen_name(response), "pin")
        self.assertContains(response, "Incorrect PIN. Please try again.")

        # The counter was saved: the second wrong PIN is the last attempt.
        response = self.go("submit_pin", {"pin": "000000"})
        self.assertContains(response, "Incorrect PIN. Last attempt remaining.")

        response = self.go("submit_pin", {"pin": "000000"})
        self.assertEqual(self.screen_name(response), "welcome")
        self.assertContains(response, "Card blocked.")
        self.assertContains(response, "Please contact your bank.")
        self.assertEqual([c["blocked"] for c in response.context["wallet"]], [True, False])
        self.assertContains(response, "BLOCKED")

        response = self.go("insert_card", {"card_number": SAVINGS_CARD})
        self.assertEqual(self.screen_name(response), "welcome")
        self.assertContains(response, "This card is blocked.")

    def test_pin_is_not_shown_again(self):
        self.go("insert_card", {"card_number": SAVINGS_CARD})
        response = self.go("submit_pin", {"pin": "654322"})
        self.assertNotContains(response, "654322")

    def test_correct_pin_opens_menu(self):
        response = self.login()
        self.assertEqual(self.screen_name(response), "menu")
        self.assertContains(response, "ATM SERVICES")
        self.assertContains(response, "Balance Inquiry")
        self.assertContains(response, "Cash Withdrawal")
        self.assertContains(response, "Change PIN")
        self.assertContains(response, "Additional Services")

    # --- withdrawal -----------------------------------------------------

    def test_withdrawal_end_to_end(self):
        self.login()
        response = self.withdraw("1000")
        self.assertEqual(self.screen_name(response), "collect")
        self.assertContains(response, "Transaction approved.")
        self.assertContains(response, "Please take your card, cash and receipt.")
        self.assertEqual(response.context["cash_text"], "PHP 1,000.00")
        self.assertEqual(response.context["receipt"].current_balance, D("14000.00"))
        self.assertContains(response, "PHP 13,500.00")  # available balance on the slip
        self.assertContains(response, 'id="dispensed-card"')

        response = self.go("collect")   # card, receipt and cash were taken
        self.assertEqual(self.screen_name(response), "welcome")
        self.login()
        self.assertEqual(self.balance_text(), "PHP 14,000.00")

    def test_invalid_amounts_rejected(self):
        self.login()
        self.press("L2")
        cases = [
            ("", INVALID),
            ("abc", INVALID),
            ("-5", POSITIVE),
            ("0", POSITIVE),
            ("50", "Minimum withdrawal is PHP 100.00."),
            ("150", "Amount must be in multiples of PHP 100."),
            ("5100", "Savings accounts allow a maximum of PHP 5000.00 per withdrawal."),
        ]
        for amount, message in cases:
            with self.subTest(amount=amount):
                response = self.go("submit_amount", {"amount": amount})
                self.assertEqual(self.screen_name(response), "withdraw_amount")
                self.assertContains(response, message)
                self.assertNotContains(response, "InvalidAmountError")
                self.assertNotContains(response, "Traceback")
        self.press("R4")  # Back to the menu
        self.assertEqual(self.balance_text(), "PHP 15,000.00")

    def test_cancel_on_confirm_changes_nothing(self):
        self.login()
        self.press("L2")
        self.go("submit_amount", {"amount": "1000"})
        response = self.go("cancel")
        self.assertEqual(self.screen_name(response), "menu")
        self.assertContains(response, "Transaction cancelled.")
        self.assertEqual(self.balance_text(), "PHP 15,000.00")

    def test_repeated_confirm_press_withdraws_once(self):
        self.login()
        self.press("L2")
        self.go("submit_amount", {"amount": "1000"})
        first = self.press("L4")    # Yes
        second = self.press("L4")   # the collect screen has no buttons
        third = self.press("L4")
        self.assertEqual(self.screen_name(first), "collect")
        self.assertEqual(self.screen_name(second), "collect")
        self.assertEqual(self.screen_name(third), "collect")
        self.assertContains(third, "Invalid selection.")
        self.go("collect")
        self.login()
        self.assertEqual(self.balance_text(), "PHP 14,000.00")

    # --- deposit and other services -------------------------------------

    def test_deposit_flow(self):
        self.login()
        self.press("R2")   # Additional Services
        response = self.press("L1")   # Cash Deposit
        self.assertContains(response, "Minimum Deposit")
        for amount, message in [
            ("50", "Minimum deposit is PHP 100.00."),
            ("250", "Amount must be in multiples of PHP 100."),
            ("250.50", "Amount must be in multiples of PHP 100."),
        ]:
            with self.subTest(amount=amount):
                response = self.go("submit_amount", {"amount": amount})
                self.assertEqual(self.screen_name(response), "deposit_amount")
                self.assertContains(response, message)
        response = self.go("submit_amount", {"amount": "300"})
        self.assertContains(response, "Deposit PHP 300.00?")
        response = self.press("L4")
        self.assertEqual(self.screen_name(response), "collect")
        self.assertContains(response, "Please take your card and receipt.")
        self.assertEqual(response.context["cash_text"], "")
        self.assertEqual(response.context["receipt"].transaction_type, "Cash Deposit")
        self.go("collect")
        self.login()
        self.assertEqual(self.balance_text(), "PHP 15,300.00")

    def test_mini_statement_and_receipt_view(self):
        self.login()
        self.withdraw("1000")
        self.go("collect")
        self.login()
        self.withdraw("500")
        self.go("collect")
        self.login()
        self.press("R2")
        response = self.press("L2")   # Mini Statement
        self.assertEqual(self.screen_name(response), "mini_statement")
        left = response.context["left"]
        self.assertEqual(left[0]["option"].label, "Cash Withdrawal 500.00")    # newest first
        self.assertEqual(left[1]["option"].label, "Cash Withdrawal 1,000.00")
        self.assertIsNone(left[2]["option"])

        response = self.press("L2")   # open the older receipt
        self.assertEqual(self.screen_name(response), "receipt_view")
        rows = dict(response.context["screen"].rows)
        self.assertEqual(rows["Amount"], "PHP 1,000.00")
        self.assertEqual(rows["Current Balance"], "PHP 14,000.00")
        self.assertEqual(rows["Available Balance"], "PHP 13,500.00")
        self.assertContains(response, "CTU")

    def test_change_pin(self):
        self.login()
        response = self.press("R1")
        self.assertEqual(self.screen_name(response), "change_pin")
        for name in ("current_pin", "new_pin", "confirm_pin"):
            self.assertContains(response, f'name="{name}"')

        response = self.go("change_pin", {
            "current_pin": SAVINGS_PIN, "new_pin": "111222", "confirm_pin": "111223",
        })
        self.assertEqual(self.screen_name(response), "change_pin")
        self.assertContains(response, "PINs do not match.")
        self.assertNotContains(response, "111222")

        response = self.go("change_pin", {
            "current_pin": SAVINGS_PIN, "new_pin": "111222", "confirm_pin": "111222",
        })
        self.assertEqual(self.screen_name(response), "menu")
        self.assertContains(response, "PIN changed successfully.")
        self.assertNotContains(response, "111222")

        self.go("eject")
        self.go("collect")
        self.go("insert_card", {"card_number": SAVINGS_CARD})
        response = self.go("submit_pin", {"pin": SAVINGS_PIN})   # old PIN
        self.assertEqual(self.screen_name(response), "pin")
        self.assertContains(response, "Incorrect PIN.")
        response = self.go("submit_pin", {"pin": "111222"})
        self.assertEqual(self.screen_name(response), "menu")

    # --- ending the session and saved state -----------------------------

    # def test_cancel_and_eject_end_session(self):
    #     self.login()
    #     response = self.go("cancel")   # Cancel on the menu removes the card
    #     self.assertEqual(self.screen_name(response), "welcome")
    #     self.assertContains(response, "Please take your card.")

    #     self.login()
    #     response = self.go("eject")
    #     self.assertEqual(self.screen_name(response), "welcome")
    #     self.assertFalse(response.context["card_inserted"])

    def test_cancel_and_eject_return_the_card(self):
        self.login()
        response = self.go("cancel")   # Cancel on the menu returns the card
        self.assertEqual(self.screen_name(response), "collect")
        self.assertContains(response, "Please take your card.")
        self.assertTrue(response.context["card_inserted"])   # it waits in the slot
        response = self.go("collect")
        self.assertEqual(self.screen_name(response), "welcome")
        self.assertFalse(response.context["card_inserted"])
        self.assertContains(response, "Please insert your card.")

        self.login()
        response = self.go("eject")
        self.assertEqual(self.screen_name(response), "collect")
        self.assertEqual(self.enabled(response), [])
        self.assertEqual(response.context["card_info"]["last_four"], "1001")
        self.assertContains(response, 'id="dispensed-card"')
        self.assertContains(response, 'id="collect-form"')
        response = self.go("collect")
        self.assertEqual(self.screen_name(response), "welcome")
        self.assertContains(response, "Thank you for using PELEC Bank.")
        self.assertContains(response, "Please insert your card.")

    def test_balance_survives_session_end(self):
        self.login()
        self.withdraw("1000")
        self.go("collect")
        self.login()
        self.assertEqual(self.balance_text(), "PHP 14,000.00")

    def test_post_only_routes(self):
        for name in POST_ROUTES:
            with self.subTest(route=name):
                response = self.client.get(reverse(f"atm_app:{name}"))
                self.assertEqual(response.status_code, 405)

    def test_out_of_step_and_empty_posts(self):
        # Nothing has been inserted yet. These inputs must change nothing.
        response = self.go("submit_pin", {"pin": SAVINGS_PIN})
        self.assertEqual(self.screen_name(response), "welcome")
        self.assertContains(response, "Please follow the instructions on the screen.")
        response = self.go("submit_amount", {"amount": "1000"})
        self.assertEqual(self.screen_name(response), "welcome")
        response = self.go("choose", {"slot": "L1"})
        self.assertContains(response, "Invalid selection.")
        response = self.go("choose")   # no slot field at all
        self.assertContains(response, "Invalid selection.")
        self.assertEqual(self.screen_name(self.go("cancel")), "welcome")
        self.assertEqual(self.screen_name(self.go("eject")), "welcome")
        response = self.go("collect")   # nothing is waiting to be collected
        self.assertEqual(self.screen_name(response), "welcome")
        self.assertContains(response, "Please follow the instructions on the screen.")

        self.go("insert_card", {"card_number": SAVINGS_CARD})
        response = self.go("submit_pin")   # no pin field at all
        self.assertEqual(self.screen_name(response), "pin")
        self.assertContains(response, "PIN must be exactly 6 digits.")
        response = self.go("submit_pin", {"pin": SAVINGS_PIN})
        self.assertEqual(self.screen_name(response), "menu")
        self.assertEqual(self.balance_text(), "PHP 15,000.00")

    def test_reset(self):
        self.go("insert_card", {"card_number": CHECKING_CARD})
        for _ in range(3):
            response = self.go("submit_pin", {"pin": "000000"})
        self.assertEqual([c["blocked"] for c in response.context["wallet"]], [False, True])

        self.login()
        self.withdraw("1000")

        response = self.go("reset")
        self.assertContains(response, "Demo reset. Sample accounts restored.")
        self.assertEqual(self.screen_name(response), "welcome")
        self.assertEqual([c["blocked"] for c in response.context["wallet"]], [False, False])
        self.login()
        self.assertEqual(self.balance_text(), "PHP 15,000.00")

    # --- security and size ----------------------------------------------

    def test_csrf_protection(self):
        # The normal test client skips CSRF checks. This one does not.
        strict = Client(enforce_csrf_checks=True)
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)

        for name in POST_ROUTES:
            with self.subTest(route=name):
                response = strict.post(reverse(f"atm_app:{name}"), {"card_number": SAVINGS_CARD})
                self.assertEqual(response.status_code, 403)

        page = self.home(client=strict)
        self.assertContains(page, 'name="csrfmiddlewaretoken"')
        token = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()
        ).group(1)
        response = strict.post(
            reverse("atm_app:insert_card"),
            {"csrfmiddlewaretoken": token, "card_number": SAVINGS_CARD},
            follow=True,
        )
        self.assertEqual(self.screen_name(response), "pin")

    def test_separate_browsers_have_separate_state(self):
        self.login()
        self.withdraw("1000")

        other = Client()
        self.assertEqual(self.screen_name(self.home(client=other)), "welcome")
        self.login(client=other)
        self.assertEqual(self.balance_text(client=other), "PHP 15,000.00")

        self.go("collect")   # first browser: take the card, cash and receipt
        self.login()
        self.assertEqual(self.balance_text(), "PHP 14,000.00")

    def test_session_size_stays_small(self):
        self.login()
        for _ in range(11):
            self.deposit("100")
        self.go("eject")
        self.go("collect")
        self.login(CHECKING_CARD, CHECKING_PIN)
        for _ in range(11):
            response = self.deposit("100", CHECKING_CARD, CHECKING_PIN)

        self.assertNotContains(response, "Session data is too large")
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertLess(len(cookie), MAX_SESSION_CHARS)
        self.assertLess(len(cookie), 4096)  # hard browser limit

        self.go("eject")
        self.go("collect")
        self.login()
        self.assertEqual(self.balance_text(), "PHP 16,100.00")

    def test_withdrawal_screen_does_not_show_the_balance(self):
        self.login()
        response = self.press("L2")
        self.assertEqual(self.screen_name(response), "withdraw_amount")
        self.assertContains(response, "Maximum Withdrawal")
        self.assertNotContains(response, "Available Balance")
        self.assertNotContains(response, "Current Balance")

    def test_welcome_screen_after_the_web_app_restarts(self):
        self.login()
        self.withdraw("1000")
        self.go("collect")
        self.login()
        # A new run of the web app has a new RUN_ID. The old screen is dropped.
        with mock.patch("atm_app.session_state.RUN_ID", "restarted"):
            response = self.home()
            self.assertEqual(self.screen_name(response), "welcome")
            self.assertFalse(response.context["card_inserted"])
            self.login()
            self.assertEqual(self.balance_text(), "PHP 14,000.00")   # balances stay

    # --- what the page shows --------------------------------------------

    def test_entry_form_matches_screen(self):
        response = self.go("insert_card", {"card_number": SAVINGS_CARD})
        self.assertContains(response, 'name="pin"')
        self.assertNotContains(response, 'name="amount"')

        response = self.go("submit_pin", {"pin": SAVINGS_PIN})   # menu.
        self.assertNotContains(response, 'name="pin"')
        self.assertNotContains(response, 'name="amount"')

        response = self.press("L2")   # withdrawal amount.
        self.assertContains(response, 'name="amount"')
        self.assertNotContains(response, 'name="pin"')

    def test_demo_help_and_card_forms(self):
        response = self.home()
        self.assertContains(response, "Demo controls")
        self.assertContains(response, "Reset demo data")
        self.assertContains(response, SAVINGS_PIN)
        self.assertContains(response, CHECKING_PIN)
        self.assertContains(response, 'name="card_number"', count=2)

        response = self.go("insert_card", {"card_number": SAVINGS_CARD})
        self.assertNotContains(response, 'name="card_number"')

    def test_receipt_paper_and_cash_drawer(self):
        response = self.login()
        self.assertIsNone(response.context["receipt"])
        self.assertContains(response, "No receipt.")

        response = self.withdraw("1000")
        self.assertIsNotNone(response.context["receipt"])
        self.assertContains(response, "Receipt printed. Click to view.")
        self.assertEqual(response.context["cash_text"], "PHP 1,000.00")
        self.assertContains(response, "Cash ready.")

        response = self.go("collect")   # everything was taken
        self.assertEqual(response.context["cash_text"], "")
        self.assertContains(response, "Empty.")
        self.assertIsNone(response.context["receipt"])