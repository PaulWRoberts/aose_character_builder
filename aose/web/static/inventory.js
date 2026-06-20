/* Container collapse toggle.
 *
 * Each container row has a ▾ button (.container-toggle) that shows/hides its
 * child rows (tr.container-child) by toggling the .container-collapsed class.
 * Rows are matched by data-instance-id. */
(function () {
    document.querySelectorAll(".container-toggle").forEach(btn => {
        btn.addEventListener("click", () => {
            const row = btn.closest("tr.container-row");
            if (!row) return;
            const instanceId = row.dataset.instanceId;
            const expanded = btn.getAttribute("aria-expanded") === "true";
            btn.setAttribute("aria-expanded", expanded ? "false" : "true");
            document.querySelectorAll(
                `tr.container-child[data-instance-id="${instanceId}"]`
            ).forEach(r => r.classList.toggle("container-collapsed"));
        });
    });
})();

/* Equipment tab switching.
 *
 * The shared equipment partial (`_equipment_ui.html`) renders a `.tabs` bar
 * plus sibling `[data-pane]` panels inside a `.equip-ui` wrapper. This lives
 * here (not sheet_overlays.js) so it works on the wizard's inline equipment
 * step, which has no overlay scrim / `.ov-body`. Delegated so it binds whether
 * the partial sits in the page flow or in the sheet drawer. */
(function () {
    document.addEventListener("click", function (e) {
        const tab = e.target.closest(".tabs .tab");
        if (!tab) return;
        const tabs = tab.closest(".tabs");
        const root = tabs.closest(".equip-ui") || tabs.parentElement;
        if (!root) return;
        tabs.querySelectorAll(".tab").forEach(x => x.classList.toggle("on", x === tab));
        root.querySelectorAll("[data-pane]").forEach(p => {
            p.hidden = (p.dataset.pane !== tab.dataset.tab);
        });
    });
})();

/* Move-destination form.
 *
 * A `.move-form` carries a `select.move-dest` whose chosen <option> holds
 * data-kind / data-id for the destination top-level (or container). On submit
 * we copy those into the form's hidden `dest_kind` / `dest_id` inputs so the
 * move-* routes receive the split fields they expect. Server-rendered options;
 * this is the only client glue.
 *
 * Auto-submit: when the form has no visible user inputs (i.e. only hidden
 * inputs + the destination select), selecting a destination immediately
 * submits. Forms with a count field (coins) are left for explicit submit. */
(function () {
    document.addEventListener("submit", function (e) {
        const form = e.target;
        if (!form.classList || !form.classList.contains("move-form")) return;
        const sel = form.querySelector("select.move-dest");
        if (!sel || sel.selectedIndex < 0) return;
        const opt = sel.options[sel.selectedIndex];
        const kind = form.querySelector("input.dest-kind");
        const id = form.querySelector("input.dest-id");
        if (kind) kind.value = opt.getAttribute("data-kind") || "";
        if (id) id.value = opt.getAttribute("data-id") || "";
    });

    document.addEventListener("change", function (e) {
        const sel = e.target;
        if (!sel.classList || !sel.classList.contains("move-dest")) return;
        const form = sel.closest("form.move-form");
        if (!form) return;
        const opt = sel.options[sel.selectedIndex];
        if (!opt || !opt.getAttribute("data-kind")) return;
        // Skip auto-submit when the form has visible (non-hidden, non-select) inputs
        const hasUserInput = form.querySelector(
            "input:not([type='hidden']), textarea"
        );
        if (hasUserInput) return;
        form.requestSubmit();
    });

    document.addEventListener("change", function (e) {
        const sel = e.target;
        if (!sel.classList || !sel.classList.contains("sell-dest")) return;
        const form = sel.closest("form.sell-form");
        if (!form) return;
        const opt = sel.options[sel.selectedIndex];
        if (!opt || !opt.value) return;
        const modeInput = form.querySelector("input[name='mode']");
        if (modeInput) modeInput.value = opt.value;
        form.requestSubmit();
    });
})();

/* Inline row-detail toggle.
 *
 * A trigger row carries data-detail-toggle="<uid>"; its detail row carries
 * data-detail-for="<uid>" and starts with class .collapsed. Clicking the
 * trigger toggles .collapsed and flips aria-expanded. Clicks that originate
 * inside a form/button/a/select are ignored so the row's own controls (cast,
 * memorise, equip, buy, etc.) keep working. Independent toggles — no sibling
 * auto-collapse. */
(function () {
    document.addEventListener("click", function (e) {
        if (e.target.closest("form, button, a, select")) return;
        const trigger = e.target.closest("[data-detail-toggle]");
        if (!trigger) return;
        const uid = trigger.getAttribute("data-detail-toggle");
        const detail = document.querySelector(`[data-detail-for="${uid}"]`);
        if (!detail) return;
        const open = !detail.classList.toggle("collapsed");
        trigger.setAttribute("aria-expanded", open ? "true" : "false");
    });
})();
