# Wizard Slice 6a — Identity Page & Alignment Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add typed class alignment restrictions with proactive combo rejection, and consolidate name + alignment + secondary skill onto one "Identity & Background" wizard page placed after Class Setup.

**Architecture:** A new pure engine module (`aose/engine/alignment.py`) computes the legal alignment set for a class combination. `post_class` rejects alignment-incompatible multi-class picks up front. The standalone `alignment` and `skill` wizard steps are replaced by one `identity` step (route + template) that also collects `name` (moved off the abilities step). The abilities step's completion marker becomes a `draft["abilities_confirmed"]` flag instead of `name`.

**Tech Stack:** Python 3, FastAPI, Jinja2, Pydantic v2, YAML data, pytest. No JS framework.

**Reference spec:** `docs/superpowers/specs/2026-05-31-wizard-identity-alignment-design.md`

**Run tests with:** `.venv\Scripts\python.exe -m pytest tests/ -q`
(The trailing `PermissionError` on `pytest-current` is a known Windows quirk — ignore it.)

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `aose/models/character_class.py` | Add typed `allowed_alignments` field | Modify |
| `data/classes/{paladin,druid,ranger,assassin}.yaml` | Populate `allowed_alignments` | Modify |
| `aose/engine/alignment.py` | Pure: intersection of class alignment sets | Create |
| `aose/web/wizard.py` | Step list, completion logic, clears, abilities POST, class POST rejection, new `identity` routes; remove `alignment`/`skill` routes | Modify |
| `aose/web/templates/wizard/identity.html` | The consolidated Identity page | Create |
| `aose/web/templates/wizard/abilities.html` | Remove the name field | Modify |
| `aose/web/templates/wizard/alignment.html` | Standalone alignment step | Delete |
| `aose/web/templates/wizard/skill.html` | Standalone skill step | Delete |
| `tests/test_alignment_engine.py` | Engine + model + class-step rejection tests | Create |
| `tests/test_wizard_identity.py` | Identity page + flow-order tests | Create |
| `tests/test_*.py` (existing flow-walking suites) | Migrate to the new flow | Modify |

---

## Task 1: Class `allowed_alignments` model field + data

**Files:**
- Modify: `aose/models/character_class.py:32-54`
- Modify: `data/classes/paladin.yaml`, `data/classes/druid.yaml`, `data/classes/ranger.yaml`, `data/classes/assassin.yaml`
- Test: `tests/test_alignment_engine.py` (new file — first tests added here)

- [ ] **Step 1: Write the failing test**

Create `tests/test_alignment_engine.py`:

```python
"""Tests for typed class alignment restrictions + the alignment engine."""
from pathlib import Path

from aose.data.loader import GameData

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_class_allowed_alignments_loaded_from_data():
    data = GameData.load(DATA_DIR)
    assert data.classes["paladin"].allowed_alignments == ["law"]
    assert data.classes["druid"].allowed_alignments == ["neutral"]
    assert data.classes["ranger"].allowed_alignments == ["law", "neutral"]
    assert data.classes["assassin"].allowed_alignments == ["neutral", "chaos"]


def test_unrestricted_classes_have_empty_allowed_alignments():
    data = GameData.load(DATA_DIR)
    for cid in ("fighter", "cleric", "thief", "magic_user", "knight", "bard"):
        assert data.classes[cid].allowed_alignments == [], cid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_alignment_engine.py -q`
Expected: FAIL — `AttributeError: 'CharClass' object has no attribute 'allowed_alignments'`.

- [ ] **Step 3: Add the model field**

In `aose/models/character_class.py`, inside `class CharClass`, add after `non_reducible_abilities` (line 54). `Literal` is already imported at the top of the file:

```python
    # Creation-time alignment restriction (typed; the descriptive `alignment`
    # feature text stays on `features` for the sheet). Empty = unrestricted
    # (any of the three). E.g. paladin=[law], ranger=[law, neutral].
    allowed_alignments: list[Literal["law", "neutral", "chaos"]] = Field(default_factory=list)
```

- [ ] **Step 4: Populate the four class YAMLs**

In `data/classes/paladin.yaml`, add a top-level key (place it just after the `shields_allowed:` line):

```yaml
allowed_alignments:
- law
```

In `data/classes/druid.yaml`:

```yaml
allowed_alignments:
- neutral
```

In `data/classes/ranger.yaml`:

```yaml
allowed_alignments:
- law
- neutral
```

In `data/classes/assassin.yaml`:

```yaml
allowed_alignments:
- neutral
- chaos
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_alignment_engine.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add aose/models/character_class.py data/classes/paladin.yaml data/classes/druid.yaml data/classes/ranger.yaml data/classes/assassin.yaml tests/test_alignment_engine.py
git commit -m "feat(class): typed allowed_alignments field + data"
```

---

## Task 2: Pure alignment engine

**Files:**
- Create: `aose/engine/alignment.py`
- Test: `tests/test_alignment_engine.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_alignment_engine.py`:

```python
from aose.engine.alignment import ALL, allowed_alignments


def _cls(data, cid):
    return data.classes[cid]


def test_allowed_alignments_single_unrestricted_is_all_three():
    data = GameData.load(DATA_DIR)
    assert allowed_alignments([_cls(data, "fighter")]) == ALL == {"law", "neutral", "chaos"}


def test_allowed_alignments_single_restricted():
    data = GameData.load(DATA_DIR)
    assert allowed_alignments([_cls(data, "paladin")]) == {"law"}
    assert allowed_alignments([_cls(data, "ranger")]) == {"law", "neutral"}


def test_allowed_alignments_intersection():
    data = GameData.load(DATA_DIR)
    # paladin [law] ∩ fighter [all] = {law}
    assert allowed_alignments([_cls(data, "paladin"), _cls(data, "fighter")]) == {"law"}
    # ranger [law, neutral] ∩ assassin [neutral, chaos] = {neutral}
    assert allowed_alignments([_cls(data, "ranger"), _cls(data, "assassin")]) == {"neutral"}


def test_allowed_alignments_empty_for_incompatible_combo():
    data = GameData.load(DATA_DIR)
    # paladin [law] ∩ assassin [neutral, chaos] = {}
    assert allowed_alignments([_cls(data, "paladin"), _cls(data, "assassin")]) == set()


def test_allowed_alignments_no_classes_is_all_three():
    assert allowed_alignments([]) == ALL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_alignment_engine.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aose.engine.alignment'`.

- [ ] **Step 3: Create the engine module**

Create `aose/engine/alignment.py`:

```python
"""Pure alignment derivation (cycle-free; imports models only).

A class with an empty ``allowed_alignments`` list is unrestricted (any of the
three). The legal alignment set for a character is the intersection across all
their classes — which may be empty for an incompatible combination.
"""
from aose.models import CharClass

ALL: set[str] = {"law", "neutral", "chaos"}


def allowed_alignments(classes: list[CharClass]) -> set[str]:
    """Intersection of each class's allowed alignments; an empty
    ``allowed_alignments`` on a class means 'all three'. Result may be empty
    (an alignment-incompatible class combination)."""
    result = set(ALL)
    for cls in classes:
        result &= set(cls.allowed_alignments) if cls.allowed_alignments else set(ALL)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_alignment_engine.py -q`
Expected: PASS (7 tests total in the file).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/alignment.py tests/test_alignment_engine.py
git commit -m "feat(engine): pure alignment intersection helper"
```

---

## Task 3: Reject alignment-incompatible class combos at the class step

**Files:**
- Modify: `aose/web/wizard.py` (`post_class`, ~line 596-668; imports near line 19)
- Test: `tests/test_alignment_engine.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_alignment_engine.py`:

```python
import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.models import RuleSet
from aose.web.app import create_app


@pytest.fixture
def mc_client(tmp_path):
    """Client with Multiclassing + Separate Race/Class on (free-form combos)."""
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, RuleSet(multiclassing=True, separate_race_class=True))
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._drafts_dir = tmp_path / "drafts"
    return client


def _seed_human_high_stats(client):
    """New draft on a human with stats high enough for paladin+assassin."""
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 13, "WIS": 13, "DEX": 15, "CON": 13, "CHA": 13}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    return draft_id


def test_class_step_rejects_alignment_incompatible_combo(mc_client):
    draft_id = _seed_human_high_stats(mc_client)
    r = mc_client.post(
        f"/wizard/{draft_id}/class", data={"class_id": ["paladin", "assassin"]}
    )
    assert r.status_code == 400
    assert "alignment" in r.text.lower()


def test_class_step_allows_alignment_compatible_combo(mc_client):
    draft_id = _seed_human_high_stats(mc_client)
    r = mc_client.post(
        f"/wizard/{draft_id}/class", data={"class_id": ["paladin", "fighter"]}
    )
    assert r.status_code == 303  # paladin [law] ∩ fighter [all] = {law}, OK
```

> Note: these tests POST `/abilities` with `data={}` (no name) and expect a 303 — that behavior is implemented in Task 4. Run this file's engine/model tests now; the two route tests above are expected to fail until Task 4 lands the abilities change. They are placed here because they assert the **class-step rejection** added in this task. After Task 4, run them again to confirm green.

- [ ] **Step 2: Run the rejection test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_alignment_engine.py::test_class_step_rejects_alignment_incompatible_combo -q`
Expected: FAIL — currently the combo is accepted (302/303) because no alignment check exists. (It may also fail on the `data={}` abilities POST until Task 4; either failure confirms the check is not yet present.)

- [ ] **Step 3: Add the import**

In `aose/web/wizard.py`, add to the engine imports block (near line 19-25):

```python
from aose.engine.alignment import allowed_alignments as _allowed_alignments
```

- [ ] **Step 4: Add the rejection in `post_class`**

In `aose/web/wizard.py`, in `post_class`, after the per-class gating loop (immediately before the race-as-class derivation block that begins `# Race-as-class (single only):`, ~line 649), insert:

```python
    # Reject alignment-incompatible multi-class combos up front so the player
    # never reaches an unsatisfiable Identity page. (Single-class is never empty.)
    if not _allowed_alignments([data.classes[c] for c in ids]):
        raise HTTPException(
            400, "These classes have incompatible alignment requirements."
        )
```

- [ ] **Step 5: Run the rejection test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_alignment_engine.py::test_class_step_rejects_alignment_incompatible_combo -q`
Expected: still FAIL **only** if the `data={}` abilities POST is the blocker (Task 4 not done). If `_seed_human_high_stats` succeeds, expect PASS. Defer the final green confirmation of the two route tests to Task 4 Step "run full suite".

- [ ] **Step 6: Commit**

```bash
git add aose/web/wizard.py tests/test_alignment_engine.py
git commit -m "feat(wizard): reject alignment-incompatible class combos at class step"
```

---

## Task 4: Identity step — backend, templates, and full test migration

This is one cohesive flow change committed as a single green unit. The standalone
`alignment`/`skill` steps disappear and `name` moves off abilities, so the entire
existing flow-walking test suite must migrate in lockstep. Order: write new
behavior tests → implement backend + templates → migrate existing tests → full
suite green → single commit.

**Files:**
- Modify: `aose/web/wizard.py` (`STEP_LABELS`, `_wizard_steps`, `_next_incomplete_step`, `_clear_after_class`, `post_abilities`; add `_identity_complete`, `get_identity`, `post_identity`, `post_identity_skill_reroll`; remove `get_alignment`, `post_alignment`, `get_skill`, `post_skill`, `post_skill_reroll`)
- Create: `aose/web/templates/wizard/identity.html`
- Modify: `aose/web/templates/wizard/abilities.html`
- Delete: `aose/web/templates/wizard/alignment.html`, `aose/web/templates/wizard/skill.html`
- Create: `tests/test_wizard_identity.py`
- Modify (migrate): see the per-file checklist in Step 9.

### Backend

- [ ] **Step 1: Write the failing identity-flow tests**

Create `tests/test_wizard_identity.py`:

```python
"""Tests for the consolidated Identity & Background step + new flow order."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _make_client(tmp_path, ruleset=None):
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._drafts_dir = tmp_path / "drafts"
    client._characters_dir = tmp_path / "characters"
    client._settings_path = settings_path
    return client


def _drive_to_identity(client, abilities=None, race="human", cls="fighter"):
    """New draft walked through to the Identity step (abilities/race/class/
    adjust/class_setup all done)."""
    abilities = abilities or {
        "STR": 13, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 13
    }
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": race})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": cls})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    return draft_id


# ── abilities no longer collects name ──────────────────────────────────────

def test_abilities_completes_without_name(tmp_path):
    client = _make_client(tmp_path)
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 13, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 13}
    save_draft(draft_id, draft, client._drafts_dir)
    r = client.post(f"/wizard/{draft_id}/abilities", data={})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft.get("abilities_confirmed") is True
    assert "name" not in draft


def test_abilities_page_has_no_name_field(tmp_path):
    client = _make_client(tmp_path)
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert 'name="name"' not in r.text


# ── flow order: identity after class_setup; old steps gone ─────────────────

def test_identity_step_sits_after_class_setup(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client)
    r = client.get(f"/wizard/{draft_id}/identity")
    assert r.status_code == 200
    # Breadcrumb order: Class Setup precedes Identity precedes Equipment.
    body = r.text
    assert body.index("Class Setup") < body.index("Identity")
    assert body.index("Identity") < body.index("Equipment")


def test_standalone_alignment_and_skill_steps_are_gone(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    # The old routes no longer exist.
    assert client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"}).status_code in (404, 405)
    assert client.get(f"/wizard/{draft_id}/skill").status_code in (404, 405)


def test_adjust_redirects_to_class_setup_not_alignment(tmp_path):
    client = _make_client(tmp_path)
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 13, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 13}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    r = client.post(f"/wizard/{draft_id}/adjust", data={})
    assert r.headers["location"] == f"/wizard/{draft_id}/class_setup"


# ── identity page content + validation ─────────────────────────────────────

def test_identity_requires_name(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client)
    r = client.post(f"/wizard/{draft_id}/identity", data={"name": "", "alignment": "law"})
    assert r.status_code == 400


def test_identity_persists_name_and_alignment_then_advances(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client)
    r = client.post(
        f"/wizard/{draft_id}/identity", data={"name": "Aragorn", "alignment": "law"}
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/equipment"
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["name"] == "Aragorn"
    assert draft["alignment"] == "law"


def test_identity_filters_alignment_options_to_class_intersection(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, cls="paladin",
                                 abilities={"STR": 13, "INT": 11, "WIS": 13,
                                            "DEX": 13, "CON": 14, "CHA": 13})
    r = client.get(f"/wizard/{draft_id}/identity")
    assert r.status_code == 200
    assert 'value="law"' in r.text
    assert 'value="chaos"' not in r.text
    assert 'value="neutral"' not in r.text


def test_identity_rejects_out_of_set_alignment(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_identity(client, cls="paladin",
                                 abilities={"STR": 13, "INT": 11, "WIS": 13,
                                            "DEX": 13, "CON": 14, "CHA": 13})
    r = client.post(
        f"/wizard/{draft_id}/identity", data={"name": "Bad", "alignment": "chaos"}
    )
    assert r.status_code == 400


# ── secondary skill section gating ─────────────────────────────────────────

def test_identity_hides_skill_section_when_rule_off(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=False))
    draft_id = _drive_to_identity(client)
    r = client.get(f"/wizard/{draft_id}/identity")
    assert "Secondary Skill" not in r.text


def test_identity_shows_and_autorolls_skill_when_rule_on(tmp_path):
    from aose.data.loader import GameData
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    r = client.get(f"/wizard/{draft_id}/identity")
    assert "Secondary Skill" in r.text
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["secondary_skill"] in GameData.load(DATA_DIR).secondary_skills


def test_identity_skill_reroll_changes_value(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")
    before = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
    for _ in range(10):
        client.post(f"/wizard/{draft_id}/identity/skill-reroll")
        after = load_draft(draft_id, client._drafts_dir)["secondary_skill"]
        if after != before:
            return
    pytest.fail("Re-roll never changed the skill after 10 tries")


def test_identity_requires_skill_when_rule_on(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    # Post a non-skill payload; skill must be supplied and valid.
    r = client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "X", "alignment": "law", "secondary_skill": "Astronaut"},
    )
    assert r.status_code == 400


# ── class change clears alignment but keeps name + secondary_skill ─────────

def test_class_change_clears_alignment_keeps_name_and_skill(tmp_path):
    client = _make_client(tmp_path, RuleSet(secondary_skills=True))
    draft_id = _drive_to_identity(client)
    client.get(f"/wizard/{draft_id}/identity")  # auto-rolls skill
    client.post(
        f"/wizard/{draft_id}/identity",
        data={"name": "Keeper", "alignment": "law",
              "secondary_skill": load_draft(draft_id, client._drafts_dir)["secondary_skill"]},
    )
    # Go back and change the class.
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "thief"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert "alignment" not in draft
    assert draft["name"] == "Keeper"
    assert "secondary_skill" in draft
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_identity.py -q`
Expected: FAIL — `/identity` routes don't exist; abilities still requires name; old steps still present.

- [ ] **Step 3: Update `STEP_LABELS` and `_wizard_steps`**

In `aose/web/wizard.py`, replace the `STEP_LABELS` dict (line 92-103) so it drops `alignment` and `skill` and adds `identity`:

```python
STEP_LABELS = {
    "rules": "Rules",
    "abilities": "Abilities",
    "race": "Race",
    "class": "Class",
    "adjust": "Ability Adjustments",
    "class_setup": "Class Setup",
    "identity": "Identity & Background",
    "equipment": "Equipment",
    "review": "Review",
}
```

Replace the body of `_wizard_steps` (line 117-128) with:

```python
    rs = _ruleset_of(draft)
    steps = ["rules", "abilities"]
    if rs.separate_race_class:
        steps.append("race")
    steps += ["class", "adjust", "class_setup", "identity", "equipment", "review"]
    return steps
```

(The `secondary_skills` rule no longer adds a step — it becomes a section inside `identity`.)

- [ ] **Step 4: Update `_next_incomplete_step` and add `_identity_complete`**

In `aose/web/wizard.py`, replace `_next_incomplete_step` (line 211-235) with:

```python
def _identity_complete(draft: dict[str, Any]) -> bool:
    """Identity is complete once name and alignment are set (and the secondary
    skill, when that rule is on)."""
    if not draft.get("name"):
        return False
    if "alignment" not in draft:
        return False
    if _ruleset_of(draft).secondary_skills and "secondary_skill" not in draft:
        return False
    return True


def _next_incomplete_step(draft: dict[str, Any]) -> str:
    # The rules step is "complete" once it has rolled abilities — at /new we
    # seed only the ruleset, so a draft without abilities is mid-rules step.
    if "abilities" not in draft:
        return "rules"
    if not draft.get("abilities_confirmed"):
        return "abilities"
    rs = _ruleset_of(draft)
    # In race-as-class mode, race_id is assigned by the class POST handler,
    # so we don't have a standalone race step to send the user to.
    if rs.separate_race_class and "race_id" not in draft:
        return "race"
    if not _has_class_pick(draft):
        return "class"
    if "ability_adjustments" not in draft:
        return "adjust"
    if not _class_setup_complete(draft):
        return "class_setup"
    if not _identity_complete(draft):
        return "identity"
    if "gold" not in draft:
        return "equipment"
    return "review"
```

- [ ] **Step 5: Update `_clear_after_class` to clear alignment**

In `aose/web/wizard.py`, replace `_clear_after_class` (line 191-194):

```python
def _clear_after_class(draft: dict[str, Any]) -> None:
    # A class change can invalidate the chosen alignment (e.g. picking paladin
    # after choosing chaos). name and secondary_skill don't depend on class.
    for k in ("ability_adjustments", "hp_roll", "hp_rolls", "proficiencies",
              "spellcasting", "spellbooks", "spells_done", "alignment"):
        draft.pop(k, None)
```

- [ ] **Step 6: Move name off the abilities POST**

In `aose/web/wizard.py`, replace `post_abilities` (line 408-418):

```python
@router.post("/{draft_id}/abilities")
async def post_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    # Name moved to the Identity step; confirming abilities is now the step's
    # completion marker. Abilities themselves are locked at draft creation.
    draft["abilities_confirmed"] = True
    save_draft(draft_id, draft, _drafts_dir(request))
    # Route via _next_incomplete_step so race-as-class drafts skip /race.
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")
```

- [ ] **Step 7: Remove the standalone alignment/skill routes; add identity routes**

In `aose/web/wizard.py`, delete these functions entirely:
- `get_alignment` and `post_alignment` (line 741-764)
- `get_skill`, `post_skill_reroll`, `post_skill` (line 780-824)

Keep the module-level helpers `_available_skills` and `_roll_skill` (line 769-777) — the identity routes reuse them.

In their place (after `post_adjust`, before the proficiency helpers), add the identity routes. `random`, `HTTPException`, `Form` are already imported; `ALIGNMENT_LABELS` is defined at module level (line 130):

```python
def _identity_alignment_options(draft: dict[str, Any], data) -> list[dict]:
    """Alignment radio options filtered to the legal set for the picked class(es)."""
    classes = [data.classes[cid] for cid in _class_ids(draft) if cid in data.classes]
    allowed = _allowed_alignments(classes)
    # Render in canonical order, keeping only allowed ones.
    return [
        {"id": a, "label": ALIGNMENT_LABELS[a]}
        for a in ("law", "neutral", "chaos")
        if a in allowed
    ]


@router.get("/{draft_id}/identity", response_class=HTMLResponse)
async def get_identity(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "identity", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    rs = _ruleset_of(draft)
    ctx = _base_context(request, draft_id, draft, "identity")
    ctx["alignments"] = _identity_alignment_options(draft, data)
    ctx["show_skill"] = rs.secondary_skills
    if rs.secondary_skills:
        skills = _available_skills(request)
        if not skills:
            raise HTTPException(
                500,
                "Secondary Skills rule is active but data/secondary_skills.yaml is empty.",
            )
        if "secondary_skill" not in draft:
            draft["secondary_skill"] = random.choice(skills)
            save_draft(draft_id, draft, _drafts_dir(request))
        ctx["skills"] = skills
        ctx["current_skill"] = draft.get("secondary_skill")
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/identity/skill-reroll")
async def post_identity_skill_reroll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    skill = _roll_skill(request)
    if skill is None:
        raise HTTPException(500, "No secondary skills configured.")
    draft["secondary_skill"] = skill
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/identity")


@router.post("/{draft_id}/identity")
async def post_identity(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    rs = _ruleset_of(draft)
    form = await request.form()

    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name required")

    alignment = form.get("alignment")
    allowed = {o["id"] for o in _identity_alignment_options(draft, data)}
    if alignment not in allowed:
        raise HTTPException(400, "Invalid alignment for the chosen class(es).")

    if rs.secondary_skills:
        secondary_skill = form.get("secondary_skill")
        if secondary_skill not in _available_skills(request):
            raise HTTPException(400, f"Unknown skill: {secondary_skill!r}")
        draft["secondary_skill"] = secondary_skill

    draft["name"] = name
    draft["alignment"] = alignment
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")
```

### Templates

- [ ] **Step 8: Edit abilities.html; create identity.html; delete old templates**

In `aose/web/templates/wizard/abilities.html`, change the heading (line 1) and remove the name `<label>` block (lines 31-35). Replace the form so it posts an empty body and uses a neutral button label:

```html
<h2>Step 1: Abilities</h2>
<p class="muted">Rolled 3d6 in order — these scores are fixed for this character.</p>

{% if subpar %}
<p class="creation-warning">
    <strong>Sub-par character:</strong> all six scores are 8 or lower. The rules
    let you start over — use <em>Cancel</em> to abandon this character and begin a
    new one if you'd like a fresh set of rolls. You may also proceed as-is.
</p>
{% endif %}
{% if rock_bottom %}
<p class="creation-note">
    {% for name in rock_bottom %}{{ name }} is 3 — extremely low.{% if not loop.last %} {% endif %}{% endfor %}
</p>
{% endif %}

<form method="post" action="/wizard/{{ draft_id }}/abilities" class="step-form">
    <table class="abilities-roll">
        <thead><tr><th>Ability</th><th>Score</th><th>Mod</th></tr></thead>
        <tbody>
        {% for ab in ability_rows %}
            <tr>
                <td>{{ ab.name }}</td>
                <td class="num">{{ ab.score }}</td>
                <td class="num">{{ "%+d"|format(ab.modifier) }}</td>
            </tr>
        {% endfor %}
        </tbody>
    </table>

    <button type="submit" class="primary">Continue &rarr;</button>
</form>
```

Create `aose/web/templates/wizard/identity.html`:

```html
<h2>Identity &amp; Background</h2>

<form method="post" action="/wizard/{{ draft_id }}/identity" class="step-form">
    <label class="field">
        <span>Character Name</span>
        <input type="text" name="name" required value="{{ draft.name or '' }}" autofocus>
    </label>

    <fieldset class="field">
        <legend>Alignment</legend>
        <div class="radio-stack">
        {% for a in alignments %}
            <label class="radio-card {% if draft.alignment == a.id %}selected{% endif %}">
                <input type="radio" name="alignment" value="{{ a.id }}" required
                       {% if draft.alignment == a.id %}checked{% endif %}>
                <span class="radio-label">{{ a.label }}</span>
            </label>
        {% endfor %}
        </div>
    </fieldset>

    {% if show_skill %}
    <fieldset class="field">
        <legend>Secondary Skill</legend>
        <p class="muted">A humble trade from before adventuring — we've rolled one;
           re-roll or pick another.</p>
        <label class="field">
            <span>Skill</span>
            <select name="secondary_skill">
                {% for s in skills %}
                <option value="{{ s }}" {% if s == current_skill %}selected{% endif %}>{{ s }}</option>
                {% endfor %}
            </select>
        </label>
    </fieldset>
    {% endif %}

    <button type="submit" class="primary">Next: Equipment &rarr;</button>
</form>

{% if show_skill %}
<form method="post" action="/wizard/{{ draft_id }}/identity/skill-reroll" class="inline-form">
    <button type="submit">Re-roll skill</button>
</form>
{% endif %}
```

Delete the old templates:

```bash
git rm aose/web/templates/wizard/alignment.html aose/web/templates/wizard/skill.html
```

- [ ] **Step 9: Migrate existing flow-walking tests**

The flow changed in three mechanical ways. Apply these transformation rules across every affected test:

**Rule A — abilities POST drops the name.**
`client.post(f"/wizard/{draft_id}/abilities", data={"name": "X"})`
becomes
`client.post(f"/wizard/{draft_id}/abilities", data={})`

**Rule B — the standalone alignment/skill steps are gone.** Delete every
`client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "..."})` and every
`/skill` GET/POST/reroll call that sat *between adjust and class_setup*.

**Rule C — collect name + alignment (+ skill) at identity, after class_setup.**
After the class_setup section completes (i.e. after `post .../hp`), add:
`client.post(f"/wizard/{draft_id}/identity", data={"name": "X", "alignment": "law"})`
— include `"secondary_skill": <a valid skill>` when the ruleset has `secondary_skills=True`. Pick the alignment from the class's legal set (e.g. paladin → `"law"`, druid → `"neutral"`).

Worked example — `tests/test_wizard.py::test_full_wizard_flow_creates_character` (lines 59-124). The relevant block changes from:

```python
    r = client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    assert r.headers["location"] == f"/wizard/{draft_id}/race"
    ...
    r = client.post(f"/wizard/{draft_id}/adjust", data={})
    assert r.headers["location"] == f"/wizard/{draft_id}/alignment"
    r = client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    assert r.headers["location"] == f"/wizard/{draft_id}/class_setup"
    r = client.post(f"/wizard/{draft_id}/hp/roll")
    ...
    r = client.post(f"/wizard/{draft_id}/hp")
    assert r.headers["location"] == f"/wizard/{draft_id}/equipment"
```

to:

```python
    r = client.post(f"/wizard/{draft_id}/abilities", data={})
    assert r.headers["location"] == f"/wizard/{draft_id}/race"
    ...
    r = client.post(f"/wizard/{draft_id}/adjust", data={})
    assert r.headers["location"] == f"/wizard/{draft_id}/class_setup"
    r = client.post(f"/wizard/{draft_id}/hp/roll")
    ...
    r = client.post(f"/wizard/{draft_id}/hp")
    assert r.headers["location"] == f"/wizard/{draft_id}/identity"
    r = client.post(f"/wizard/{draft_id}/identity", data={"name": "Thorin", "alignment": "law"})
    assert r.headers["location"] == f"/wizard/{draft_id}/equipment"
```

Apply the three rules to each file below. After editing, run that file's tests
to confirm green before moving on (command in Step 10).

  - [ ] `tests/test_wizard.py` — `test_full_wizard_flow_creates_character`, `test_unique_id_on_name_collision`, `test_race_rejected_if_abilities_too_low` (only Rule A needed for the last, since it stops at race). `test_gate_redirects_to_first_incomplete_step` already expects `/abilities` — keep.
  - [ ] `tests/test_secondary_skills.py` — heavy rewrite. The whole file is built around the standalone `/skill` step, which no longer exists. Rewrite its helper `_start_draft_at` to drive through `class_setup` (Rule A; drop the `/alignment` post at line 92's flow). Replace every `/skill`-route assertion with the identity-section behavior: the skill section now lives on `/identity` and reroll is `/identity/skill-reroll`. Tests asserting old redirect targets (`/skill`, `/class_setup`) must target `/identity` / `/equipment`. The sheet-rendering tests (skill persists to character/print) keep their assertions but reach finalize via the identity POST. Move any genuinely skill-section-specific coverage that overlaps `tests/test_wizard_identity.py` and delete duplicates.
  - [ ] `tests/test_wizard_back_nav.py` — `_start` helper (line 40) + inline calls at lines 58,68,86,98,102,119,133,136,155,158,172,175,201,204. Apply Rules A/B/C. Breadcrumb back-nav assertions that referenced the `Alignment`/`Secondary Skill` steps must reference `Identity & Background`; the abilities back-link assertion (`href=".../abilities"`) still holds once abilities is confirmed.
  - [ ] `tests/test_wizard_class_setup.py` — `_drive_to_class_setup` (line 243) and inline calls at 156,169,253,363,367,411,415,425,429,456,460. Note `_drive_to_class_setup` currently posts `/alignment` *before* class_setup (line 253) — remove that (Rule B); class_setup no longer depends on alignment. `_breadcrumb` order assertions update to the new step list.
  - [ ] `tests/test_wizard_race.py` — `_drive_dwarf_fighter_to_finalize` (line 102) + inline calls at 105,109,135,138,159,172,184,197,208,224,228. Apply A/B/C; finalize path needs the identity POST.
  - [ ] `tests/test_race_as_class.py` — `_start` (line 70) + calls at 81,87,93,107,118,126,135,145,155,168,214,216,232,235,249,252. Race-as-class still requires name → it goes on identity now. Alignment options come from the single race-as-class class (all unrestricted → all three).
  - [ ] `tests/test_multiclassing.py` — `_start_elf` (line 112), `_to_hp` (line 216) + calls at 118,200,222,253,273,297. The `/alignment` posts (neutral) move to identity. For elf fighter/magic_user combos alignment is unrestricted; keep `"neutral"`.
  - [ ] `tests/test_wizard_rules_step.py` — `_start` (line 48) + calls at 137,149,168,171,193,196,217,241,244,273. Rule-change clear assertions: where a test changed class and asserted downstream clears, add an assertion that `alignment` is now cleared too (matches Task 4 Step 5). Apply A/B/C otherwise.
  - [ ] `tests/test_wizard_ability_adjust.py` — `_drive_to_adjust` (line 177) + calls at 181,191,200,202,227,257. The asserts that `adjust` redirects to `/alignment` (line 227) and that GET `/alignment` renders (lines 191,202) change to `/class_setup` / `/identity` respectively.
  - [ ] `tests/test_weapon_proficiency.py` — `_start_fighter` (line 176), `_start_magic_user` (line 190) + the `/alignment` posts at 186,200. Apply A/B; proficiencies are part of class_setup (before identity), so these helpers stop before identity — just drop the alignment posts and the name on abilities.
  - [ ] `tests/test_spell_routes.py` — `_start_caster_draft` (line 85) + calls at 94,98,107,111. Spells are a class_setup section (before identity); drop the `/alignment` posts and the name on abilities.
  - [ ] `tests/test_settings.py` — `_run_wizard_to_completion` (line 159), `_start_draft_with` (line 210) + the `/alignment` posts at 169,222. `_run_wizard_to_completion` reaches finalize → needs the identity POST with the `name` parameter it already threads through.
  - [ ] `tests/test_demihuman_rules.py`, `tests/test_containers.py`, `tests/test_choice_rules.py`, `tests/test_equipment.py`, `tests/test_equip_attacks.py`, `tests/test_magic_items.py` — each has ~2 flow-walking call sites (per the audit). Apply Rules A/B/C; for the equipment/containers/magic suites the helper must now pass through `/identity` before `/equipment`.

- [ ] **Step 10: Run the full suite to verify green**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all tests pass (the prior count was 577 + the new identity/alignment tests; the standalone-skill tests in `test_secondary_skills.py` are folded into the identity behavior). Investigate and fix any failure before committing — do not commit red.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat(wizard): Slice 6a — Identity page + alignment filtering"
```

---

## Self-Review (run by the plan author; recorded for the executor)

**Spec coverage**
- §1 typed class alignment data → Task 1. ✅
- §2 pure engine helper → Task 2. ✅
- §3 reject incompatible combos at class step → Task 3. ✅
- §4 identity step (consolidation + reorder), abilities loses name + `abilities_confirmed`, identity page (name/alignment/skill + reroll), completion rule → Task 4 Steps 3-8. ✅
- §5 `_clear_after_class` also clears `alignment`, keeps name + skill → Task 4 Step 5 (+ test in `test_wizard_identity.py`). ✅
- §6 tests (all six bullets) → Task 1/2/3 tests + `test_wizard_identity.py` + the migration. ✅
- Risks: name-contract change handled by the migration (Rule A + identity POST); knight modelled as unrestricted (empty list, Task 1 leaves it empty); no migration needed (nothing deployed). ✅

**Type consistency**
- `allowed_alignments` (field, engine fn, route helper) used consistently; route imports it aliased as `_allowed_alignments` to avoid colliding with the module function name in `wizard.py`.
- New step id `identity` consistent across `STEP_LABELS`, `_wizard_steps`, `_next_incomplete_step`, `_gate`, routes, and template filename.
- `abilities_confirmed` set in `post_abilities`, read in `_next_incomplete_step`.
- `_identity_complete` / `_identity_alignment_options` defined before use.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-31-wizard-identity-alignment.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
