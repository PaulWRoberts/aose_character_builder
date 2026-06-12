from aose.web.settings_routes import (
    RULE_LABELS, RULE_DESCRIPTIONS, IMPLEMENTED_RULES, SOURCE_RULES, flatten_rule_fields,
)


def test_combat_talents_registered_and_implemented():
    assert "combat_talents" in RULE_LABELS
    assert "combat_talents" in RULE_DESCRIPTIONS
    assert "combat_talents" in IMPLEMENTED_RULES  # never renders a "pending" badge


def test_combat_talents_attached_to_carcass_crawler_1():
    fields = flatten_rule_fields(SOURCE_RULES["carcass_crawler_1"])
    assert "combat_talents" in fields
