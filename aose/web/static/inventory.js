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
