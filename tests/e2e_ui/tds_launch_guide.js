/**
 * TDS Launch Guide — scenario navigator (tests/e2e_ui only)
 */
(function () {
  const SCENARIOS = {
    s1: {
      title: "S1 — Flag OFF (launch default)",
      body: `
        <p><strong>Setup:</strong> <code>TDS_ACCRUAL_ENABLED=false</code> in .env (default).</p>
        <p><strong>Steps:</strong> Partner records balance → completes job.</p>
        <p><strong>Expected:</strong> Balance saved; <code>tds.skipped=true</code>; ledger empty.</p>
        <p><strong>E2E UI:</strong> <a href="index.html">Sprint 2</a> → uncheck “TDS accrual enabled” → Accrual simulator.</p>
        <p><strong>pytest:</strong> <code>tests/test_service_lifecycle_balance.py</code></p>
      `,
    },
    s2: {
      title: "S2 — Flag ON · entity_type NULL",
      body: `
        <p><strong>Setup:</strong> <code>TDS_ACCRUAL_ENABLED=true</code>; pujari without <code>entity_type</code> (~139/144 today).</p>
        <p><strong>Steps:</strong> Partner tries confirm-balance while <code>in_progress</code>.</p>
        <p><strong>Expected:</strong> <strong>422</strong> — entire transaction rolls back; <code>balance_collected_at</code> stays NULL; complete → 409.</p>
        <p><strong>Fix target:</strong> Decouple PR — balance saves; intent parks in ops queue.</p>
        <p><strong>pytest:</strong> <code>tests/test_tds_accrual.py</code></p>
      `,
    },
    s3: {
      title: "S3 — Flag ON · compliant pujari",
      body: `
        <p><strong>Setup:</strong> <code>entity_type</code> + <code>pan_hash</code> set (admin tax-compliance API).</p>
        <p><strong>Steps:</strong> confirm-balance with full offline amount → complete.</p>
        <p><strong>Expected:</strong> 200; 1 accrual row; <code>pujari_tax_year</code> updated.</p>
        <p><strong>Live staging UUID:</strong> pujari <code>0827e851-b4b3-40fe-935d-4990f5ed9ba3</code></p>
        <p><strong>E2E UI:</strong> Sprint 2 → Inspect booking (Test ops id).</p>
      `,
    },
    s4: {
      title: "S4 — FY crosses ₹5L threshold",
      body: `
        <p><strong>Setup:</strong> Individual/HUF + PAN; <code>fy_gross_before</code> just below ₹5,00,000.</p>
        <p><strong>Expected:</strong> 0% until crossed; then <strong>0.1% on this transaction</strong> (not retro on first ₹5L — CA Q1b may differ).</p>
        <p><strong>E2E UI:</strong> Sprint 2 → TDS calculator — set FY gross 490000, txn 2100.</p>
        <p><strong>pytest:</strong> <code>tests/e2e/test_sprint2_tds_launch_e2e.py</code></p>
      `,
    },
    s5: {
      title: "S5 — No PAN on file",
      body: `
        <p><strong>Setup:</strong> <code>pan_hash</code> NULL; accrual enabled.</p>
        <p><strong>Expected:</strong> <strong>5%</strong> on transaction gross (platform self-funds deposit until Phase 3).</p>
        <p><strong>E2E UI:</strong> Sprint 2 → uncheck “PAN on file” → Compute TDS.</p>
      `,
    },
    s6: {
      title: "S6 — Partial acknowledgement + complete (P0 defect)",
      body: `
        <p><strong>Setup:</strong> <code>amount_due_offline=2100</code>; body <code>{"method":"cash","amount":1}</code>.</p>
        <p><strong>Expected today:</strong> Balance saved at ₹1; <strong>complete succeeds</strong> — wrong.</p>
        <p><strong>Target:</strong> No silent partial complete — block or route to ops/dispute with shortfall (<code>L-SPRINT-2-BALANCE-PARTIAL-COMPLETE</code>).</p>
        <p><strong>pytest gap:</strong> add test when fixing lifecycle.</p>
      `,
    },
    s7: {
      title: "S7 — PAN accept gate (launch-incompatible)",
      body: `
        <p><strong>Setup:</strong> <code>PAN_ACCEPT_GATE_ENABLED=true</code>; pujari without PAN.</p>
        <p><strong>Expected:</strong> <strong>422</strong> on <code>POST …/offers/{id}/accept</code> — dispatch supply collapses at ~3% PAN coverage.</p>
        <p><strong>E2E UI:</strong> Sprint 2 → PAN accept gate panel.</p>
        <p><strong>Do not enable at launch.</strong></p>
      `,
    },
    s8: {
      title: "S8 — TDS reversal on dispute",
      body: `
        <p><strong>Wired:</strong> Admin dispute <code>offline_non_payment</code> after balance recorded → reversal ledger entry.</p>
        <p><strong>Not wired:</strong> dispute <code>service</code>; admin refund override.</p>
        <p><strong>pytest:</strong> <code>tests/test_admin_slice3.py::test_dispute_offline_non_payment_reverses_tds</code></p>
      `,
    },
  };

  const grid = document.getElementById("scenarioGrid");
  const titleEl = document.getElementById("scenarioDetailTitle");
  const bodyEl = document.getElementById("scenarioDetailBody");

  function selectScenario(id) {
    const s = SCENARIOS[id];
    if (!s) return;
    document.querySelectorAll(".tds-scenario").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.scenario === id);
    });
    titleEl.textContent = s.title;
    bodyEl.innerHTML = s.body;
  }

  grid?.addEventListener("click", (e) => {
    const btn = e.target.closest(".tds-scenario");
    if (btn?.dataset.scenario) selectScenario(btn.dataset.scenario);
  });

  // Nav highlight on scroll
  const navLinks = document.querySelectorAll(".tds-nav-link");
  const sections = document.querySelectorAll(".tds-section");

  function onScroll() {
    let current = "overview";
    sections.forEach((sec) => {
      const top = sec.getBoundingClientRect().top;
      if (top <= 120) current = sec.id;
    });
    navLinks.forEach((a) => {
      a.classList.toggle("active", a.dataset.section === current);
    });
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
})();
