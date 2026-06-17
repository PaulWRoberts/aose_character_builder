from aose.models import CharacterSpec, Retainer


def _spec(name="Hero", **kw):
    return CharacterSpec(
        name=name, abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                              "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter"}],
        alignment="neutral", **kw)


def test_spec_defaults_to_no_retainers():
    assert _spec().retainers == []


def test_retainer_wraps_a_spec_and_round_trips():
    ret = Retainer(id="r1", spec=_spec("Torchbearer"), loyalty=7, role="light")
    pc = _spec(retainers=[ret])
    again = CharacterSpec.model_validate(pc.model_dump())
    assert again.retainers[0].spec.name == "Torchbearer"
    assert again.retainers[0].loyalty == 7
    assert again.retainers[0].spec.retainers == []   # bounded recursion


def test_old_save_without_retainers_loads():
    raw = _spec().model_dump()
    raw.pop("retainers")
    assert CharacterSpec.model_validate(raw).retainers == []
