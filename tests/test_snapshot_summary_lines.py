"""資產快照：行事曆結果行（2026-11-24）。"""
import importlib
import sys
import types


def _load():
    sys.modules.setdefault("supabase", types.SimpleNamespace(create_client=lambda *a, **k: None))
    return importlib.import_module("record_snapshot")


def test_summary_lines_categories_and_total():
    rs = _load()
    lines = rs.summary_lines({"grand_total": 1500, "total_twd": 1000, "total_cost": 800, "total_pnl": 200,
                              "cumulative_dividend": 10, "tw_stock": 600, "us_stock": 400, "kifutong": 0,
                              "scb": 0, "taishin": 0, "bank_total": 500, "other_assets_total": 500})
    assert lines[0] == "快照／總資產：1,500"
    assert "快照／股票：台股 600、美股 400" in lines
    assert lines[-1] == "快照／其他資產：銀行 500；小計 500"
