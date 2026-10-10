# TDS Decision Memo — s.393 (ex-194-O) facilitation withholding

**Status:** SKELETON — to be sent in launch prep. **Owner (sender):** [OWNER: TBD].
**Send-by:** [DATE: TBD]. **Store signed ref in:** `tax_statutory_config.advisor_signoff_ref`.
**Companion:** [`TDS_LAUNCH_STATUS.md`](./TDS_LAUNCH_STATUS.md), [`SPEC_AMENDMENTS.md §16`](./SPEC_AMENDMENTS.md), `GST_Withholding_Tax_Model_v1.2.pdf`.

> **Context for the CA (one paragraph):** Mana Guruji is an e-commerce operator (ECO) facilitating
> puja services between customers and independent pujaris in Hyderabad. At launch the pujari
> collects the puja fee **offline in cash directly from the customer**; the platform charges only a
> small online booking fee (~₹61) via Razorpay and **never holds the puja value**. ~139 of 144
> pujaris currently have **no PAN on file**. We need your position on s.393/194-O deduction, deposit,
> and — critically — recovery, given we never touch the money.

---

## Q-recovery (QUESTION ONE — blocks the deduction model)

The platform never holds the offline puja value, yet **s.194-O(1) deems the direct
customer→pujari payment to be paid by the ECO**, so the deduction obligation appears to stand.

1. Confirm the obligation applies to offline-collected pujas under the deeming provision.
2. **Lawful mechanism + timing to recover TDS from the pujari** when we never held the funds —
   net from a future payout, raise a recoverable invoice/debit, or collect upfront?
3. Is an **interim OFF posture** (compute nothing, deduct nothing, monitor exposure, remediate via
   `catch_up` once the pipeline is live) acceptable while (1)/(2) are resolved?
4. Given many no-PAN pujaris, what is the fastest defensible path before FY crosses **₹5 lakh**
   (mandatory PAN gate at accept vs PAN drive with deadline)? **v3:** 5% is fail-safe **above**
   ₹5L only, not on all GMV below threshold.

---

## Q1 — Gross basis

Spec §16 (Example B) reads s.393 as applying to the **full puja value, both online and offline
portions**, excluding our platform booking fee. Confirm:
- Full puja value is the correct gross (not just the platform-handled slice).
- Booking fee (our own supply) is correctly **excluded** from the pujari's facilitation gross.
- Treatment of **partial collection** (pujari acknowledges less than full).

## Q1b — Threshold crossing & retroactivity

- On the transaction that crosses ₹5L for a PAN individual/HUF, is TDS on the **full transaction
  value** or only the amount **above ₹5L**?
- Retroactivity: once crossed, is TDS owed on earlier below-threshold gross (drives `catch_up`)?

## Q2 — Rate & PAN

- Confirm current rates: **0.1%** (post-Oct-2024, Finance (No.2) Act 2024), **5%** no/invalid PAN
  (s.206AA proviso for 194-O), **₹5L** threshold for individual/HUF-with-PAN only.
- **Operative vs present PAN:** we propose fail-safe-high (unverified/inoperative → 5%). Confirm.
- PAN storage for filing: encrypted plaintext PAN retained for 26Q/Form 16A.

## Q3 — Deposit, filing, forms

- Deposit calendar (7th of next month; 30 Apr for March); challan mechanics.
- **26Q** quarterly; **Form 16A** issuance; TRACES registration.
- Confirm the correct forms (spec previously referenced Form 140/131 — likely wrong).

## Q4 — Reversals

- FY reversal policy when an offline collection is reversed/refunded (contra entry timing,
  cross-FY handling).

## Q5 — TCS §52 (informational; build ON HOLD)

- Any TCS interaction to flag now (no build requested).

---

## Sign-off

| Field | Value |
|-------|-------|
| CA name / firm | |
| Membership no. | |
| Date | |
| `advisor_signoff_ref` | |
| Scope confirmed | Q-recovery, Q1, Q1b, Q2, Q3, Q4 |
