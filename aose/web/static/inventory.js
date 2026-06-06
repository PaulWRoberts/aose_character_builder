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
