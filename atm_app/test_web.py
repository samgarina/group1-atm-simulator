from django.test import TestCase
from django.urls import reverse


class ATMURLTests(TestCase):

    def test_dashboard_url_resolves(self):
        url = reverse("atm_app:dashboard")
        self.assertEqual(url, "/")

    def test_deposit_url_resolves(self):
        url = reverse("atm_app:deposit")
        self.assertEqual(url, "/deposit/")

    def test_withdraw_url_resolves(self):
        url = reverse("atm_app:withdraw")
        self.assertEqual(url, "/withdraw/")

    def test_reset_url_resolves(self):
        url = reverse("atm_app:reset")
        self.assertEqual(url, "/reset/")


class ATMPlaceholderViewTests(TestCase):

    def test_dashboard_view_returns_200(self):
        response = self.client.get(reverse("atm_app:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_deposit_view_returns_200(self):
        response = self.client.get(reverse("atm_app:deposit"))
        self.assertEqual(response.status_code, 200)

    def test_withdraw_view_returns_200(self):
        response = self.client.get(reverse("atm_app:withdraw"))
        self.assertEqual(response.status_code, 200)


    def test_reset_view_returns_200(self):
        response = self.client.get(reverse("atm_app:reset"))
        self.assertEqual(response.status_code, 200)

class ATMResetViewTests(TestCase):

    def test_reset_restores_starting_balance(self):
        # Get the original starting balance
        initial_response = self.client.get(
            reverse("atm_app:dashboard")
        )
        starting_balance = initial_response.context["balance"]

        # Make a deposit so the balance changes
        self.client.post(
            reverse("atm_app:deposit"),
            {"amount": "100"}
        )

        # Reset the account
        response = self.client.post(
            reverse("atm_app:reset"),
            follow=True
        )

        self.assertEqual(response.status_code, 200)

        # Get the balance after resetting
        final_balance = response.context["balance"]

        self.assertEqual(final_balance, starting_balance)


class WebFlowTests(TestCase):
    """End-to-end browser workflow tests across ATM screens."""

    @staticmethod
    def _val(obj, key):
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def _first_card_and_pin(self, response):
        wallet = response.context["wallet"]
        demo_help = response.context["demo_help"]
        card = next(c for c in wallet if not self._val(c, "blocked"))
        pin = next(
            self._val(row, "pin")
            for row in demo_help
            if self._val(row, "last_four") == self._val(card, "last_four")
        )
        return self._val(card, "card_number"), pin

    def _login(self):
        res = self.client.get(reverse("atm_app:dashboard"))
        card_number, pin = self._first_card_and_pin(res)
        res = self.client.post(
            reverse("atm_app:insert_card"),
            {"card_number": card_number},
            follow=True,
        )
        res = self.client.post(
            reverse("atm_app:submit_pin"),
            {"pin": pin},
            follow=True,
        )
        return res, card_number, pin

    def _choose(self, response, keyword):
        slots = list(response.context["left"]) + list(response.context["right"])
        match = next(
            item
            for item in slots
            if self._val(item, "option")
            and keyword.lower() in self._val(self._val(item, "option"), "label").lower()
        )
        return self.client.post(
            reverse("atm_app:choose"),
            {"slot": self._val(match, "slot")},
            follow=True,
        )

    def test_welcome_screen_renders_wallet_and_demo_controls(self):
        res = self.client.get(reverse("atm_app:dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._val(res.context["screen"], "name"), "welcome")
        self.assertGreater(len(res.context["wallet"]), 0)

    def test_insert_card_and_valid_pin_reaches_menu(self):
        res, _, _ = self._login()
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(self._val(res.context["screen"], "name"), ("welcome", "pin"))

    def test_invalid_pin_stays_on_pin_screen(self):
        res = self.client.get(reverse("atm_app:dashboard"))
        card_number, _ = self._first_card_and_pin(res)
        self.client.post(
            reverse("atm_app:insert_card"),
            {"card_number": card_number},
            follow=True,
        )
        res = self.client.post(
            reverse("atm_app:submit_pin"),
            {"pin": "0000"},
            follow=True,
        )
        self.assertEqual(self._val(res.context["screen"], "name"), "pin")

    def test_deposit_and_withdraw_web_flow(self):
        res, _, _ = self._login()
        res = self._choose(res, "deposit")
        self.assertEqual(self._val(res.context["screen"], "input_mode"), "amount")
        res = self.client.post(
            reverse("atm_app:submit_amount"),
            {"amount": "500"},
            follow=True,
        )
        self.assertEqual(res.status_code, 200)

    def test_change_pin_flow(self):
        res, _, old_pin = self._login()
        res = self._choose(res, "pin")
        self.assertEqual(self._val(res.context["screen"], "input_mode"), "change_pin")
        res = self.client.post(
            reverse("atm_app:change_pin"),
            {
                "current_pin": old_pin,
                "new_pin": "6543",
                "confirm_pin": "6543",
            },
            follow=True,
        )
        self.assertEqual(res.status_code, 200)

    def test_cancel_and_collect_returns_to_welcome(self):
        res, _, _ = self._login()
        res = self.client.post(reverse("atm_app:cancel"), follow=True)
        self.assertEqual(self._val(res.context["screen"], "name"), "collect")
        res = self.client.post(reverse("atm_app:collect"), follow=True)
        self.assertEqual(self._val(res.context["screen"], "name"), "welcome")