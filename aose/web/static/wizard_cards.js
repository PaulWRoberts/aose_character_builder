/* Wizard card interactions: book modal (race/class), collapse/clear,
   multiclass cap, spell expander + Learn. One delegated controller. */
(function () {
  "use strict";

  const overlay = document.getElementById("wizard-detail");

  /* ---------- overlay open/close ---------- */
  function openOverlay() { if (overlay) overlay.classList.add("on"); }
  function closeOverlay() { if (overlay) overlay.classList.remove("on"); }

  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-close]")) { closeOverlay(); return; }
    if (overlay && overlay.classList.contains("on") &&
        !e.target.closest("#wizard-detail .ov-head, #wizard-detail .ov-body, #wizard-detail .ov-foot")) {
      // scrim click (the overlay backdrop) closes
      if (e.target === overlay) closeOverlay();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeOverlay();
  });

  /* ---------- detail modal + selection ---------- */
  let activeCard = null;

  function gridOf(card) { return card.closest(".card-grid"); }
  function inputOf(card) { return card.querySelector('input[name="race_id"], input[name="class_id"]'); }

  function applySingleCollapse(grid, card) {
    grid.querySelectorAll(".card").forEach(c => c.classList.toggle("selected", c === card));
    grid.classList.add("collapsed");
    if (window.csValidate) window.csValidate();
  }

  function clearSingle(grid) {
    grid.querySelectorAll(".card").forEach(c => {
      c.classList.remove("selected");
      const i = inputOf(c); if (i) i.checked = false;
    });
    grid.classList.remove("collapsed");
    if (window.csValidate) window.csValidate();
  }

  function multiCount(grid) {
    return grid.querySelectorAll('input[name="class_id"]:checked').length;
  }

  function refreshMulti(grid) {
    const cap = parseInt(grid.dataset.cap || "0", 10);
    const atCap = multiCount(grid) >= cap;
    grid.querySelectorAll(".card").forEach(c => {
      const i = inputOf(c);
      c.classList.toggle("selected", !!(i && i.checked));
    });
    grid.classList.toggle("collapsed", atCap);
    if (window.csValidate) window.csValidate();
  }

  function selectCard(card) {
    const grid = gridOf(card);
    const input = inputOf(card);
    if (!input) return;
    if (grid.hasAttribute("data-multi")) {
      input.checked = true;
      refreshMulti(grid);
    } else {
      input.checked = true;
      applySingleCollapse(grid, card);
    }
  }

  function openDetail(card) {
    activeCard = card;
    overlay.querySelector('[data-role="title"]').textContent = card.dataset.name || "Detail";
    overlay.querySelector('[data-role="body"]').innerHTML =
      card.querySelector(".detail-body").innerHTML;
    const selectBtn = overlay.querySelector('[data-role="select"]');
    if (card.dataset.available === "0") {
      selectBtn.disabled = true;
      selectBtn.textContent = card.dataset.reason || "Unavailable";
    } else {
      selectBtn.disabled = false;
      selectBtn.textContent = "Select";
    }
    openOverlay();
  }

  document.addEventListener("click", function (e) {
    // Clear button on a card.
    const clearBtn = e.target.closest(".card-clear");
    if (clearBtn) {
      e.preventDefault();
      const grid = gridOf(clearBtn.closest(".card"));
      if (grid.hasAttribute("data-multi")) {
        const i = inputOf(clearBtn.closest(".card")); if (i) i.checked = false;
        refreshMulti(grid);
      } else {
        clearSingle(grid);
      }
      return;
    }
    // Select button inside the overlay.
    if (e.target.closest('#wizard-detail [data-role="select"]')) {
      if (activeCard && activeCard.dataset.available !== "0") selectCard(activeCard);
      closeOverlay();
      return;
    }
    // Card click → open detail (ignore clicks on the raw input/clear button).
    const card = e.target.closest(".card[data-detail]");
    if (card && !e.target.closest("input, .card-clear")) {
      e.preventDefault();
      openDetail(card);
    }
  });

  /* ---------- spell expander + Learn ---------- */
  function refreshSpellGrid(grid) {
    const required = parseInt(grid.dataset.required, 10);
    const cards = Array.from(grid.querySelectorAll(".spell-card"));
    const learned = cards.filter(c => c.querySelector(".spell-checkbox").checked).length;
    cards.forEach(card => {
      const box = card.querySelector(".spell-checkbox");
      const btn = card.querySelector(".btn-learn");
      card.classList.toggle("learned", box.checked);
      card.classList.toggle("selected", box.checked);
      btn.textContent = box.checked ? "Forget" : "Learn";
      btn.disabled = !box.checked && learned >= required;
    });
    const counter = grid.parentElement.querySelector(".spell-counter");
    if (counter) counter.textContent = "Picked " + learned + " of " + required + ".";
    if (window.csValidate) window.csValidate();
  }

  document.addEventListener("click", function (e) {
    // Learn / Forget toggle.
    const learn = e.target.closest(".btn-learn");
    if (learn) {
      e.preventDefault();
      const card = learn.closest(".spell-card");
      const box = card.querySelector(".spell-checkbox");
      const grid = card.closest(".spell-grid");
      const required = parseInt(grid.dataset.required, 10);
      const learned = grid.querySelectorAll(".spell-checkbox:checked").length;
      if (!box.checked && learned >= required) return;  // cap reached
      box.checked = !box.checked;
      refreshSpellGrid(grid);
      return;
    }
    // Expand/collapse the card (ignore clicks on the Learn button).
    const spellCard = e.target.closest(".spell-card[data-spell]");
    if (spellCard && !e.target.closest(".btn-learn, input")) {
      spellCard.classList.toggle("expanded");
    }
  });

  document.querySelectorAll(".spell-grid[data-required]").forEach(refreshSpellGrid);
})();
