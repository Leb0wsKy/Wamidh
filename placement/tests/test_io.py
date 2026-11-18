from placement.io import normalise_name


def test_normalise_name_ignores_accents_case_and_spacing() -> None:
    assert normalise_name("Béja") == normalise_name("beja") == "beja"
    assert normalise_name("  Ben  Arous ") == "ben arous"
