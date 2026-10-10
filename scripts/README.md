# Scripts

## `export_tds_26q.py`

Read-only CSV for CA 26Q / RPU prep: `--month=YYYY-MM` or `--fy=YYYY --quarter=N` (Indian FY quarters). **`amount_on_which_tds_deducted`** is the ledger taxable-base net for the period (26Q “amount paid/credited on which tax deducted”), not total facilitation turnover. **PAN** is left blank — supply operative PANs out-of-band from KYC for the few pujaris over ₹5L.
