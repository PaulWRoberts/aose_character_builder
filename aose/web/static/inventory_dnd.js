/* Inventory drag-and-drop + container collapse.
 *
 * Listens for drag/drop events on rows tagged with data-source / data-target
 * (added by _equipment_ui.html in Task 18) and POSTs to /equipment/move.
 * On success the page reloads to pick up the new server-rendered state.
 *
 * The URL prefix is read from the wrapper element's data-equipment-url-prefix
 * attribute, so the same JS works on both the sheet and the wizard. */
(function () {
    const equipmentRoot = document.querySelector("[data-equipment-url-prefix]");
    if (!equipmentRoot) return;
    const URL_PREFIX = equipmentRoot.dataset.equipmentUrlPrefix;

    // ── Container collapse ─────────────────────────────────────────
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

    // ── Drag-and-drop ──────────────────────────────────────────────
    let dragged = null;

    document.querySelectorAll('[draggable="true"]').forEach(el => {
        el.addEventListener("dragstart", e => {
            dragged = el;
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/plain", el.dataset.itemId || "");
        });
        el.addEventListener("dragend", () => {
            dragged = null;
            document.querySelectorAll(".drag-over")
                .forEach(n => n.classList.remove("drag-over"));
        });
    });

    document.querySelectorAll("[data-target], .container-row")
        .forEach(target => {
            target.addEventListener("dragover", e => {
                if (!dragged) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                target.classList.add("drag-over");
            });
            target.addEventListener("dragleave", () => {
                target.classList.remove("drag-over");
            });
            target.addEventListener("drop", async e => {
                e.preventDefault();
                target.classList.remove("drag-over");
                if (!dragged) return;
                // Derive source key from the dragged element
                let source = dragged.dataset.source || "";
                if (!source && dragged.classList.contains("container-row")) {
                    source = `container_row:${dragged.dataset.instanceId}`;
                }
                // Derive target key
                let targetKey = target.dataset.target || "";
                if (!targetKey && target.classList.contains("container-row")) {
                    targetKey = `container:${target.dataset.instanceId}`;
                }
                if (!source || !targetKey) return;
                const itemId = dragged.dataset.itemId || "";
                const instanceId = dragged.dataset.instanceId || "";
                const form = new FormData();
                form.append("source", source);
                form.append("target", targetKey);
                form.append("item_id", itemId);
                if (instanceId) form.append("instance_id", instanceId);
                const resp = await fetch(`${URL_PREFIX}/move`, {
                    method: "POST", body: form,
                });
                if (resp.ok || resp.status === 303) {
                    window.location.reload();
                } else {
                    const msg = await resp.text();
                    alert("Move failed: " + msg);
                }
            });
        });
})();
