import json

from mcd_host.cli import main


def run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr().out
    return code, out


def test_demo_plan_json(capsys):
    code, out = run(["demo", "--people", "6", "--budget", "300", "--json"], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    data = payload["data"]
    assert data["people"] == 6
    assert data["payable"] <= 30000
    assert data["perPerson"] > 0
    assert any(line["kind"] == "set" for line in data["lines"])


def test_plan_requires_menu_or_demo(capsys):
    code, out = run(["plan", "--people", "4", "--json"], capsys)
    assert code == 1
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "菜单" in payload["error"]["message"]


def test_demo_writes_card(capsys, tmp_path):
    target = tmp_path / "card.svg"
    code, _ = run(["demo", "--people", "4", "--budget", "200", "-o", str(target)], capsys)
    assert code == 0
    svg = target.read_text(encoding="utf-8")
    assert svg.startswith("<svg")
    assert "人均" in svg


def test_card_round_trip(capsys, tmp_path):
    plan_path = tmp_path / "plan.json"
    card_path = tmp_path / "card.svg"
    code, out = run(["plan", "--demo", "--people", "4", "--budget", "200", "--json"], capsys)
    assert code == 0
    plan_path.write_text(out, encoding="utf-8")
    code, _ = run(["card", "--plan", str(plan_path), "-o", str(card_path)], capsys)
    assert code == 0
    svg = card_path.read_text(encoding="utf-8")
    assert "麦门东道主" in svg


def test_fetch_rejects_write_tools(capsys):
    from mcd_host.mcp import MCPClient, MCPError

    client = MCPClient(token="test-token")
    try:
        client.call_tool("create-order", {})
    except MCPError as exc:
        assert "只读" in str(exc)
    else:
        raise AssertionError("应当拒绝写操作工具")
