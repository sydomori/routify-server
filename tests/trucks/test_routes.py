def _create(client, headers, plate="KAA 111A"):
    return client.post("/trucks", json={"plate_number": plate, "model": "Isuzu"}, headers=headers)

def test_manager_creates_and_lists(client, manager, auth_headers):
    h = auth_headers(manager)
    r = _create(client, h)
    assert r.status_code == 201 and r.json["driver"] is None
    assert len(client.get("/trucks", headers=h).json) == 1