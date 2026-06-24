# AOSE Character Builder — feature changelog

Reverse-chronological ledger of landed features. Each entry is a one-line
summary plus its branch and spec/plan. **The full design detail lives in the
linked `docs/superpowers/{specs,plans}/` files** — this is just the index.
For the living architecture (how the subsystems fit together *now*), see
[ARCHITECTURE.md](ARCHITECTURE.md).

| Date | Feature | Branch | Spec/Plan slug |
|---|---|---|---|
| 2026-06-24 | Retainer hiring follows hiring PC's class/edition/demihuman rules: shared availability predicates; Advanced race picker; content/edition gating; demihuman class+level-cap enforcement; optional human benefits | feat/retainer-hiring-rules | 2026-06-24-retainer-hiring-rules |
| 2026-06-23 | Movement consolidation finish: spell sources carry `location`, move through `move_thing`; capacity gate unified (animals/vehicles/containers); carrier casting gate (carried-only cast/decipher/copy); equipped-weapon double-render fix; stash/stow/load helpers deleted from shop+companions, 12 routes removed; shared `act_move` for all row actions; magic Drop+Sell, enchanted/spell-source Drop, spell-source Move | feat/movement-consolidation-finish | 2026-06-23-movement-consolidation-finish |
| 2026-06-23 | Unified item movement: every owned thing (incl. magic/enchanted/ammo, now location-aware) moves to any inventory or container via one `move_thing` engine front-door + single `POST /inventory/move`; stacking types split-and-merge; moving unloads ammo/weapons; shared `_actions.html` macros + sheet-wide button-size standard | feat/unified-item-movement | 2026-06-23-unified-item-movement-and-shared-controls |
| 2026-06-23 | Interaction-hub follow-up: coin/gem/jewellery stacks in the box are now clickable → per-stack modals (`coin_modal`/`gem_modal`/`jewellery_modal`) carrying convert/move/adjust/drop (coins), sell-one/sell-all/±1/move/drop (gems), mark-damaged/sell/move/drop (jewellery); per-item modal exposes Sell ▾ + Drop for carried/stashed; drawer Treasure tab stripped to add-forms only; treasure Move restricted to top-level carriers (no orphan into container/retainer) | main | 2026-06-22-inventory-box-interaction-hub |
| 2026-06-22 | Inventory box becomes the interaction hub: all owned-item management (equip/stash/move/use-as-container) in the box; `OwnerCaps` drives three-section pane layout (Equipped · Coins · Carried/Stowed); drawer stripped to acquisition-only (Shop/Enchant/Scribe/Treasure); `use_as_container` route on sheet + wizard; retainer containers via `_find_container_anywhere`; wizard equipment step renders live box above drawer | feat/inventory-box-interaction-hub | 2026-06-22-inventory-box-interaction-hub |
| 2026-06-22 | Cast spells from scrolls in the spell list (Read Magic unlock for arcane, language gate for divine, duplicate charges, inline cast/decipher buttons in Documents tab) | feat/scroll-casting-spell-list | 2026-06-22-scroll-casting-in-spell-list |
| 2026-06-22 | Companions section redesigned as a collapsed ledger: `<details>`/`<summary>` rows (Retainers → Animals → Vehicles), at-a-glance summary (name, descriptor, loyalty red ≤ 4, HP/Hull stepper) with the full stat block hidden until expand; new `/retainer/{id}/hp` route + `companions.js` open-row persistence; old `.companion-*` card CSS removed | main | — |
| 2026-06-21 | Animal/retainer equip-unequip + click-to-modal in inventory box | main | 2026-06-21-animal-retainer-equip |
| 2026-06-20 | Unified expandable inventory box (all top-level inventories as collapsible accordion in col 3; rich equipped display per group; nested containers; coins anywhere; Other Possessions pane; generalized Move from any location; Spells to full-width; Companions shed storage UI) | feat/unified-inventory-box | 2026-06-20-unified-inventory-box |
| 2026-06-19 | Prime-requisite XP bonus is now data-driven per class (`CharClass.xp_bonus_tiers`): fixes multi-prime classes (e.g. halfling reeve with both primes ≥13 now gets +10%, not +5%) where the old lowest-score lookup was wrong; added missing prime-req feature text to 7 CC1/CC3 classes; `ClassAdvancement.xp_bonus_pct` shows the applied bonus on the sheet | main | — |
| 2026-06-19 | Coin UI consolidation follow-up: coins render as line-items everywhere via a shared `coin_table` macro (full Move dropdown to any location, in-place Convert, Adjust); removed the legacy coin-chip strip + Coin Purse popover; read-only total-wealth readout; move-* routes map an invalid `StorageLocation` to 400 instead of 500 | feat/companions-and-holdings | inventory-consolidation |
| 2026-06-19 | Inventory consolidation: located coins/treasure (CoinStack + StorageLocation), top-level inventory groups, lowest-first shop spend, storage movement engine | feat/companions-and-holdings | inventory-consolidation |
| 2026-06-18 | Zine form controls: tightened the global `input`/`select`/`textarea` baseline — condensed Oswald data fields, compact 26px box, inked CSS caret replacing native select chrome (was 14px Bitter + fat padding, oversized & off-typeface) | feat/companions-and-holdings | — |
| 2026-06-17 | Companions bug-fix pass: shop `equipment_buy` now dispatches Animal/Vehicle to roster instances (were landing in carried inventory → no cards rendered); carriers gain a Load form (mirrors retainer Give/Take); section retitled "Companions & Vehicles" + zine-styled | feat/companions-and-holdings | animals-and-vehicles |
| 2026-06-17 | Retainers (Companions & Holdings Phase B): hired classed NPCs, loyalty, CHA cap, XP −50%, promote normal human, PC↔retainer transfer | feat/companions-and-holdings | 2026-06-17-retainers |
| 2026-06-16 | Animals & vehicles (Companions & Holdings Phase A) | feat/companions-and-holdings | animals-and-vehicles |
| 2026-06-16 | Wizard book-style detail modals + trimmed race/spell cards | main | 2026-06-16-wizard-detail-modals |
| 2026-06-12 | Fix: innate abilities now usable — spell-style pip rows + dedicated Use/Restore modal | main | — |
| 2026-06-12 | CC5 Cantrips optional rule (+ Read Magic Cantrip) | feat/cc5-cantrips | 2026-06-12-cc5-cantrips |
| 2026-06-12 | Combat Talents (CC1) + level-up choice mechanism | feat/combat-talents | 2026-06-12-combat-talents |
| 2026-06-12 | Hosted auth & multi-tenancy: invite-only GCIP Google sign-in, per-user workspaces, export/import | feat/hosted-auth-multitenancy | 2026-06-11-hosted-auth-multitenancy |
| 2026-06-11 | CC2/4/5 races & classes: Wood Elf, Halfling Hearthsinger, Halfling Reeve, Arcane Bard, Ratling, Changeling (class + race duals); Goblin/Wolf Hunter conditional `attack`/`damage` grants; `dryad` language | feat/cc2-4-5-races-classes | — |
| 2026-06-10 | Source-organized content & optional rules: per-category `disabled_content`, source-panel settings/wizard UI, `SOURCE_RULES` dependency tree | feature/source-content-rules-organization | source-content-rules-organization |
| 2026-06-10 | Interactive wizard rolls + Class Setup consolidation: roll-first feature choices & secondary skill, consolidated save-and-advance, client-side selection caps | feat/interactive-wizard-rolls | 2026-06-10-interactive-wizard-rolls |
| 2026-06-10 | Individual initiative optional rule: DEX-derived initiative modifier in the Combat box (clickable breakdown) + halfling/human bonuses; generic `mechanical.requires_rule` feature gating | feat/individual-initiative | 2026-06-10-individual-initiative |
| 2026-06-10 | CC3 races/classes + feature-choice mechanic & innate abilities | feat/cc3-races-classes | 2026-06-10-cc3-races-and-classes |
| 2026-06-10 | Wield capacity: named hand slots (main_hand/off_hand), two-weapon fighting rule, dual-wield penalties (−2/−4), gargantua 1H-2H melee exception | main | 2026-06-10-wield-capacity-equip |
| 2026-06-09 | CC3 expanded equipment + parametric weapon qualities | main | 2026-06-09-cc3-expanded-equipment |
| 2026-06-08 | Gargantua feature automation: Rock Throwing synthetic weapon + Open Doors STR-category bump | `main` | `2026-06-08-gargantua-feature-automation` |
| 2026-06-08 | Fix race/race-as-class feature bleed: race-as-class is self-contained (no race features/grants/ability-mods); migrated grants onto race-locked class files | `main` | — |
| 2026-06-08 | CC1 classes & races: Acolyte, Mage, Gargantua, Goblin, Hephaestan (class + race duals) | `main` | — |
| 2026-06-08 | Inventory item modals (properties + safe actions) & shop property expander | `feat/inventory-item-modals` | `2026-06-08-inventory-item-modals` |
| 2026-06-08 | Conditional attack-roll modifiers (mirrors conditional AC) | `main` | `2026-06-08-conditional-attack-modifiers` |
| 2026-06-07 | Situational "vs X" save bonuses (`save:vs:*`) | `main` | `2026-06-07-situational-save-bonuses` |
| 2026-06-07 | Conditional Armour Class modifiers | `main` | `2026-06-07-conditional-ac-modifiers` |
| 2026-06-07 | Languages, literacy & WIS magic-save improvements | `feature/languages-literacy-wisdom-saves` | (11-task plan) |
| 2026-06-07 | Weighted secondary-skill distribution + roll-for-two | `main` | `2026-06-06-weighted-secondary-skills` |
| 2026-06-06 | Feature-granted modifiers (`GrantedModifier`/`Scaling`) | `main` | (7-task plan) |
| 2026-06-06 | Mental-powers caster type + Kineticist class | `main` | `2026-06-06-mental-powers-and-kineticist` |
| 2026-06-06 | Content-source tagging & filtering | `main` | `2026-06-06-content-sources` |
| 2026-06-04 | OSR-zine sheet redesign (prototype-3 port) | `feature/sheet-redesign` | `2026-06-04-character-sheet-redesign` |
| 2026-06-04 | Adventuring-gear cleanup, stackable buys, container consolidation | `main` | `2026-06-04-adventuring-gear-cleanup` |
| 2026-06-03 | Faithful encumbrance, treasure weight & multi-coin currency | `main` | `2026-06-03-encumbrance-treasure-currency` |
| 2026-06-03 | Gems & jewellery (free, weightless, sheet-only treasure) | `feature/gems-and-jewellery` | `2026-06-03-gems-and-jewellery` |
| 2026-06-03 | Spell books & scrolls (owned documents, copy/cast) | `feature/spell-books-scrolls` | `2026-06-03-spell-books-and-scrolls` |
| 2026-06-02 | Magic-item compendium bulk import (Phase 2) | `main` | `2026-06-02-magic-item-import` |
| 2026-06-02 | Ammunition (separate item type, magic-ammo composition) | `feature/ammunition` | `2026-06-02-ammunition` |
| 2026-06-02 | Magic-item enchantment composition model (Phase 1) | `main` | `2026-06-02-magic-item-enchantments` |
| 2026-06-02 | Manual rolls + Strict Mode | `main` | `2026-06-02-manual-rolls-strict-mode` |
| 2026-06-02 | On-sheet play state (current HP, prepared slots, rest) | — | `2026-06-02-on-sheet-character-state` |
| (earlier) | Spell selection (known-vs-prepared) | `feature/spell-selection` | `2026-05-29-spell-selection` |
| (earlier) | Multi-classing (Multiple Classes optional rule) | — | `2026-05-29-spell-selection` (shares `quiet-soaring-hedgehog`) |
| (earlier) | Magic items (data-driven `Modifier` system) | `main` | `2026-05-28-magic-items` |
| (earlier) | Container items | — | `2026-05-27-container-items` |

## Notes worth keeping out of the spec files

- Test counts cited at landing time, for rough provenance: enchantment
  composition 834, ammunition (9-task), magic-item import 882, spell
  books/scrolls 924, gems & jewellery 959, encumbrance/treasure/currency 1020,
  weighted secondary skills 1225, situational save bonuses 1291. Run the suite
  for the current number.
- Several features were explicitly scoped *out* at landing time and may resurface
  as future work: cursed scrolls / treasure maps; `saddle_bags` and the Transport
  table; Gloves of Dexterity & Periapt of Proof Against Poison effects (carry
  `# TODO:` data comments); action-gated attack bonuses (acrobat tumbling,
  assassin assassination); magic-item `save:vs:*` catalog encoding.
