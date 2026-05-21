def test_rf_dashboard_displays_chamber_and_qr(client):
    response = client.get("/rf-chamber/")
    assert response.status_code == 200
    body = response.data
    assert b"XL001" in body
    assert b"data:image/png;base64" in body
