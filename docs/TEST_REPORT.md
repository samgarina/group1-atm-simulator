# ATM Simulator — Test Report

**Author:** Kim Jacob O. Garciano  
**Date:** November 18, 2026  
**Branch:** `docs/garciano-test-report` -> `develop`  

---

## Six-Case End-to-End Browser Test Matrix

| Case | Scenario | Steps & Input | Expected Result | Actual Result | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **Card Insertion & Valid PIN** | Open `/`, click **Insert card**, pick an active card from the wallet, enter its valid starting PIN, and press **Enter**. | Monitor switches from `welcome` to `pin`, then unlocks the main ATM transaction menu. | Card inserted cleanly, PIN prompt rendered, and valid starting PIN unlocked the main transaction screen. | **PASS** |
| **2** | **Invalid PIN Rejection** | Insert a card and submit an incorrect PIN (`0000`). | Stays on the `pin` screen and displays a readable invalid PIN error message. | Remained on `pin` screen and displayed a readable error alert without granting account access. | **PASS** |
| **3** | **Valid Deposit** | Select **Deposit**, enter a valid multiple of `PHP 100` (e.g., `500`), and submit. | Balance increases by `PHP 500.00`, success feedback is shown, and a receipt slip is generated. | Balance updated by `+PHP 500.00`, confirmation message rendered, and receipt slip populated with transaction details. | **PASS** |
| **4** | **Valid Withdrawal** | Select **Withdraw**, enter a valid multiple of `PHP 100` within limits (e.g., `1000`), and submit. | Balance decreases by `PHP 1,000.00`, cash appears in the dispenser tray, and a receipt is printed. | Balance decreased by `PHP 1,000.00`, cash became available in the dispenser tray, and receipt printed accurately. | **PASS** |
| **5** | **Overdraft / Limit / Invalid Amount** | Attempt a withdrawal exceeding available balance / transaction limit, or enter a non-multiple of `PHP 100` (e.g., `150`). | Transaction is rejected with a readable error message and the account balance remains unchanged. | Rejected with readable validation/error message; balance remained unchanged and no invalid transaction was recorded. | **PASS** |
| **6** | **Cancel, Collect & Demo Reset** | Press **Cancel** to end session and collect card, then click **Reset demo data**. | Screen moves to `collect`, returns to `welcome` after collecting, and **Reset demo data** restores starting balances. | Dispensed card on `collect` screen, returned to `welcome` upon collection, and **Reset demo data** restored initial balances. | **PASS** |