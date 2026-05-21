def test_inventory_dashboard_lists_items(client):
    response = client.get("/inventory/")
    assert response.status_code == 200
    assert b"Spectrum Analyzer" in response.data
