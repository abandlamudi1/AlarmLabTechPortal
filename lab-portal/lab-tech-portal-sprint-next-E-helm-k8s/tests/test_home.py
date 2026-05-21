def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Lab Tech Portal" in response.data


def test_resources_page(client):
    response = client.get("/resources")
    assert response.status_code == 200
    assert b"Lab Tech Resources" in response.data
    assert b"Lab Request Ticket Guide" in response.data
