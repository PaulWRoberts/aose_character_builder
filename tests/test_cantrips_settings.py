from aose.web.settings_routes import (
    RULE_LABELS, RULE_DESCRIPTIONS, IMPLEMENTED_RULES, SOURCE_RULES,
    flatten_rule_fields, parse_ruleset_from_form,
)


def test_cantrip_rules_registered_and_implemented():
    for field in ("cantrips", "read_magic_cantrip"):
        assert field in RULE_LABELS
        assert field in RULE_DESCRIPTIONS
        assert field in IMPLEMENTED_RULES  # never renders a "pending" badge


def test_cantrip_rules_attached_to_carcass_crawler_5():
    fields = flatten_rule_fields(SOURCE_RULES["carcass_crawler_5"])
    assert "cantrips" in fields
    assert "read_magic_cantrip" in fields


def test_read_magic_cantrip_forced_off_when_cantrips_off():
    # read_magic_cantrip checked but its parent cantrips unchecked -> forced off
    form = {"read_magic_cantrip": "on"}
    rs = parse_ruleset_from_form(form)
    assert rs.cantrips is False
    assert rs.read_magic_cantrip is False


def test_read_magic_cantrip_kept_when_cantrips_on():
    form = {"cantrips": "on", "read_magic_cantrip": "on"}
    rs = parse_ruleset_from_form(form)
    assert rs.cantrips is True
    assert rs.read_magic_cantrip is True
