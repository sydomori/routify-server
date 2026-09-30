def _create(client, headers, plate="KAA 111A"):
    return client.post("/api/trucks", json={"plate_number": plate, "model": "Isuzu"}, headers=headers)

def test_manager_creates_and_lists(client, manager, auth_headers):
    h = auth_headers(manager)
    r = _create(client, h)
    assert r.status_code == 201 and r.json["driver"] is None
    assert len(client.get("api/trucks", headers=h).json) == 1

def test_driver_cannot_create_but_can_list(client, driver, manager, auth_headers):
    _create(client, auth_headers(manager))
    dh = auth_headers(driver)
    assert _create(client, dh, "KBB 222B").status_code == 403
    # make_user defaults must_change_password=False, so the driver fixture
    # is never gated by @password_change_required here.
    assert client.get("/api/trucks", headers=dh).status_code == 200