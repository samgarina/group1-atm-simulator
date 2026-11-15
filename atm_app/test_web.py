from decimal import Decimal
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


class ATMIntegrationFlowTests(TestCase):

    def test_full_deposit_withdraw_and_reset_flow(self):
        # GET dashboard
        initial_response = self.client.get(reverse("atm_app:dashboard"))
        self.assertEqual(initial_response.status_code, 200)
        starting_balance = Decimal(str(initial_response.context["balance"]))

        # POST deposit
        deposit_response = self.client.post(
            reverse("atm_app:deposit"),
            {"amount": "500"},
            follow=True,
        )
        self.assertEqual(deposit_response.status_code, 200)
        self.assertEqual(
            Decimal(str(deposit_response.context["balance"])),
            starting_balance + Decimal("500.00"),
        )

        # POST withdraw
        withdraw_response = self.client.post(
            reverse("atm_app:withdraw"),
            {"amount": "200"},
            follow=True,
        )
        self.assertEqual(withdraw_response.status_code, 200)
        self.assertEqual(
            Decimal(str(withdraw_response.context["balance"])),
            starting_balance + Decimal("300.00"),
        )

        # POST reset
        reset_response = self.client.post(
            reverse("atm_app:reset"),
            follow=True,
        )
        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(
            Decimal(str(reset_response.context["balance"])),
            starting_balance,
        )

    def test_overdraft_shows_readable_error_and_leaves_balance_unchanged(self):
        res = self.client.get(reverse("atm_app:dashboard"))
        balance = Decimal(str(res.context["balance"]))

        # Drain available funds within valid bill/limit steps so next withdrawal triggers overdraft
        for _ in range(10):
            if balance < Decimal("5000.00"):
                break
            res = self.client.post(
                reverse("atm_app:withdraw"),
                {"amount": "5000"},
                follow=True,
            )
            new_balance = Decimal(str(res.context["balance"]))
            if new_balance == balance:
                break
            balance = new_balance

        # Attempt overdraft withdrawal
        overdraft_response = self.client.post(
            reverse("atm_app:withdraw"),
            {"amount": "5000"},
            follow=True,
        )
        self.assertEqual(overdraft_response.status_code, 200)

        # Balance must remain unchanged
        self.assertEqual(
            Decimal(str(overdraft_response.context["balance"])),
            balance,
        )

        # Readable error message must be shown
        messages_list = [str(m) for m in overdraft_response.context.get("messages", [])]
        page_text = overdraft_response.content.decode().lower()
        self.assertTrue(
            bool(messages_list)
            or any(
                term in page_text
                for term in ("insufficient", "minimum", "not enough", "exceeds", "error")
            )
        )