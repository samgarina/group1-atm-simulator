# ATM Simulator — Test Report

**Author:** Kim Jacob O. Garciano  
**Date:** November 18, 2026  
**Branch:** `docs/garciano-test-report` $\rightarrow$ `develop`  

---

## Six-Case End-to-End Browser Test Matrix

| Case | Scenario | Steps & Input | Expected Result | Actual Result | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **Card Insertion & Valid PIN** | Open `/`, click **Insert card**, pick an active card from the wallet, enter its valid starting PIN, and press **Enter**[cite: 4]. | Monitor switches from `welcome` to `pin`, then unlocks the main ATM transaction menu[cite: 4]. | *Pending afternoon browser session* | Pending |
| **2** | **Invalid PIN Rejection** | Insert a card and submit an incorrect PIN (`0000`)[cite: 4]. | Stays on the `pin` screen and displays a readable invalid PIN error message[cite: 4]. | *Pending afternoon browser session* | Pending |
| **3** | **Valid Deposit** | Select **Deposit**, enter a valid multiple of `PHP 100` (e.g., `500`), and submit[cite: 4]. | Balance increases by `PHP 500.00`, success feedback is shown, and a receipt slip is generated[cite: 4]. | *Pending afternoon browser session* | Pending |
| **4** | **Valid Withdrawal** | Select **Withdraw**, enter a valid multiple of `PHP 100` within limits (e.g., `1000`), and submit[cite: 4]. | Balance decreases by `PHP 1,000.00`, cash appears in the dispenser tray, and a receipt is printed[cite: 4]. | *Pending afternoon browser session* | Pending |
| **5** | **Overdraft / Limit / Invalid Amount** | Attempt a withdrawal exceeding available balance / transaction limit, or enter a non-multiple of `PHP 100` (e.g., `150`)[cite: 4]. | Transaction is rejected with a readable error message and the account balance remains unchanged[cite: 4]. | *Pending afternoon browser session* | Pending |
| **6** | **Cancel, Collect & Demo Reset** | Press **Cancel** to end session and collect card, then click **Reset demo data**[cite: 4]. | Screen moves to `collect`, returns to `welcome` after collecting, and **Reset demo data** restores starting balances[cite: 4]. | *Pending afternoon browser session* | Pending |