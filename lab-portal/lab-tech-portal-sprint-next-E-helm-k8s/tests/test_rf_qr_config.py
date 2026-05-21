from tools.rf_chamber import rf_chamber_app as rf_module


def test_build_chamber_link_respects_base_url(app):
    with app.test_request_context("/"):
        app.config["RF_CHAMBER_BASE_URL"] = "https://portal.example.com"
        link = rf_module._build_chamber_link("LG015")
        assert link == "https://portal.example.com/rf-chamber/edit/LG015"


def test_build_chamber_link_falls_back_to_external(client):
    response = client.get("/rf-chamber/")
    assert response.status_code == 200
    with client.application.test_request_context("/"):
        client.application.config["RF_CHAMBER_BASE_URL"] = ""
        link = rf_module._build_chamber_link("XL001")
        assert link.startswith("http://")
        assert link.endswith("/rf-chamber/edit/XL001")
