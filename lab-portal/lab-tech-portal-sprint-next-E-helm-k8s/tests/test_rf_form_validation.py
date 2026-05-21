from tools.rf_chamber import rf_chamber_app as rf_module


def test_validate_requires_chamber_id_and_size():
    errors = rf_module._validate({
        "barcode": "",
        "size": "",
        "ports": "",
        "purpose": "",
        "location": "",
        "owner": "",
    })
    assert errors["barcode"] == "Chamber ID is required."
    assert errors["size"] == "Size is required."
