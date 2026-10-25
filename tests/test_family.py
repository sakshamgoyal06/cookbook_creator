from sqlalchemy import select

from models.database import get_engine
from models.schema import events
from services import dish_service, family_service, project_service
from test_screens import _onboard


def _book_token(pid):
    return project_service.get_project(pid)["book_token"]


def test_family_joins_and_asks_for_dishes_that_wait_for_the_buyers_ok(app, auth_client):
    pid = _onboard(auth_client)
    token = _book_token(pid)
    riya = app.test_client()
    page = riya.get(f"/b/{token}/join").data.decode()
    assert "Join the family cookbook" in page and "Rajma" in page and "ne poocha hai" in page

    done = riya.post(f"/b/{token}/join", data={"name": "  Riya ", "dish_other": "Kadhi pakora"})
    assert "Thank you, Riya" in done.data.decode()
    riya.post(f"/b/{token}/join", data={"name": "Riya S", "dish": "Rajma"})  # same phone: same member, renamed
    members = [m["name"] for m in project_service.get_members(pid)]
    assert members == ["Aarav", "Riya S"]
    assert "Ask for another dish" in riya.get(f"/b/{token}/join").data.decode()

    dishes = {d["title"]: d for d in dish_service.list_dishes(pid)}
    assert dishes["Kadhi pakora"]["status"] == "requested" and dishes["Kadhi pakora"]["source"] == "family"
    assert dishes["Rajma"]["requested_by_label"] == "Riya S"  # "+1" on an existing dish
    assert dish_service.next_dish(pid)["title"] == "Rajma"  # requests don't jump the queue unapproved

    home = auth_client.get(f"/p/{pid}").data.decode()
    assert "Riya asked for Kadhi pakora" in home
    family = auth_client.get(f"/p/{pid}/family").data.decode()
    assert "Waiting for your OK" in family and f"/b/{token}/join" in family
    kadhi = dishes["Kadhi pakora"]["id"]
    auth_client.post(f"/p/{pid}/family/requests/{kadhi}", data={"decision": "approve"})
    assert dish_service.get_dish(pid, kadhi)["status"] == "wishlist"
    assert "asked by Riya" in auth_client.get(f"/p/{pid}/recipes").data.decode()

    # The buyer re-saving their own list keeps the family's dishes.
    auth_client.post(f"/p/{pid}/setup/dishes", data={"dishes": "Chole"})
    assert {d["title"] for d in dish_service.list_dishes(pid)} >= {"Kadhi pakora", "Chole"}
    with get_engine().connect() as conn:
        names = conn.execute(select(events.c.name)).scalars().all()
    assert names.count("family_member_joined") == 1 and names.count("dish_requested") == 2


def test_hidden_requests_and_removed_members(app, auth_client):
    pid = _onboard(auth_client)
    token = _book_token(pid)
    joker = app.test_client()
    joker.post(f"/b/{token}/join", data={"name": "Bunty", "dish_other": "Maggi"})
    maggi = family_service.pending_requests(pid)[0]
    auth_client.post(f"/p/{pid}/family/requests/{maggi['id']}", data={"decision": "hide"})
    assert family_service.pending_requests(pid) == []
    assert dish_service.get_dish(pid, maggi["id"])["status"] == "skipped"
    member = project_service.get_members(pid)[-1]
    auth_client.post(f"/p/{pid}/family/members/{member['id']}/remove")
    assert [m["name"] for m in project_service.get_members(pid)] == ["Aarav"]
    buyer = project_service.get_members(pid)[0]
    auth_client.post(f"/p/{pid}/family/members/{buyer['id']}/remove")  # the organiser can't be removed
    assert len(project_service.get_members(pid)) == 1


def test_join_needs_a_name_and_a_live_link(app, auth_client):
    pid = _onboard(auth_client)
    token = _book_token(pid)
    anon = app.test_client()
    assert anon.post(f"/b/{token}/join", data={"name": " "}).status_code == 400
    assert anon.get("/b/nope/join").status_code == 404
    auth_client.post(f"/p/{pid}/family/new-link")
    assert anon.get(f"/b/{token}/join").status_code == 404
    assert anon.get(f"/b/{_book_token(pid)}/join").status_code == 200
