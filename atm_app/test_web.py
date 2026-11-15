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