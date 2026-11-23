"""Tool registry. Each tool declares *prerequisites* that the factory checks
deterministically - the LLM may propose a tool, but it is only attached if the
prerequisite holds and its justification quote can be found in the requirements."""
from __future__ import annotations

import ast
import csv
import datetime as _dt
import json
import operator
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests


@dataclass
class Tool:
    name: str
    description: str
    when_to_use: str
    parameters: dict
    fn: Callable
    prerequisite: str  # human readable
    # signals: words in requirements that would legitimately call for the tool
    signals: tuple = ()

    def schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


# --------------------------------------------------------------------------- calculator
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_FUNCS = {"round": round, "min": min, "max": max, "abs": abs, "sum": lambda *a: sum(a)}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        if isinstance(node.op, ast.Pow) and abs(_eval(node.right)) > 100:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("unsupported expression")


def calculator(expression: str) -> dict:
    expr = expression.replace("^", "**").replace(",", "").replace("$", "").replace("%", "/100")
    expr = re.sub(r"(?<=\d)\s*[x×]\s*(?=\d)", "*", expr)
    try:
        val = _eval(ast.parse(expr, mode="eval"))
        if isinstance(val, float):
            val = round(val, 4)
        return {"expression": expression, "result": val}
    except Exception as e:
        return {"expression": expression, "error": f"could not evaluate: {e}"}


# --------------------------------------------------------------------------- current date
def current_date() -> dict:
    now = _dt.datetime.now()
    return {"date": now.strftime("%Y-%m-%d"), "weekday": now.strftime("%A"), "time": now.strftime("%H:%M")}


# --------------------------------------------------------------------------- weather (open-meteo, keyless)
def weather_forecast(location: str, days: int = 3) -> dict:
    try:
        g = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": location, "count": 1}, timeout=10).json()
        if not g.get("results"):
            return {"error": f"location '{location}' not found"}
        r = g["results"][0]
        f = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": r["latitude"], "longitude": r["longitude"], "timezone": "auto",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                "forecast_days": max(1, min(int(days), 7)),
            },
            timeout=10,
        ).json()
        return {"location": f"{r['name']}, {r.get('country', '')}", "daily": f.get("daily", {})}
    except Exception as e:
        return {"error": f"weather service unavailable: {e}"}


# --------------------------------------------------------------------------- CSV lookup
_CSV_FILES: list[str] = []  # set by the runtime from the agent's knowledge folder


def set_csv_files(paths: list[str]) -> None:
    _CSV_FILES.clear()
    _CSV_FILES.extend(paths)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def csv_lookup(query: str, column: str = "", max_rows: int = 8) -> dict:
    """Keyword search over all rows (optionally restricted to one column). Rows are
    ranked by how many query terms they contain; exact cell matches rank first."""
    if not _CSV_FILES:
        return {"error": "no CSV files available"}
    terms = [t for t in _norm(query).split() if len(t) > 1]
    hits = []
    for path in _CSV_FILES:
        with open(path, newline="", encoding="utf-8", errors="ignore") as fh:
            for row in csv.DictReader(fh):
                cells = {k: v for k, v in row.items() if k}
                if column:
                    col = next((k for k in cells if _norm(k) == _norm(column)), None)
                    hay = _norm(cells.get(col, "")) if col else ""
                else:
                    hay = _norm(" ".join(cells.values()))
                if not hay:
                    continue
                exact = any(_norm(v) == _norm(query) for v in cells.values())
                score = sum(1 for t in terms if re.search(rf"\b{re.escape(t)}", hay)) + (10 if exact else 0)
                if score:
                    hits.append((score, Path(path).name, cells))
    hits.sort(key=lambda x: -x[0])
    best = hits[0][0] if hits else 0
    rows = [dict(r, _source=f) for s, f, r in hits if s >= max(1, best * 0.6)][: int(max_rows)]
    return {"query": query, "matches": len(rows), "rows": rows}


# --------------------------------------------------------------------------- registry
REGISTRY: dict[str, Tool] = {
    "csv_lookup": Tool(
        name="csv_lookup",
        description="Look up rows in the tabular (CSV) knowledge files by keyword, part number, name or code. Returns matching rows with all columns.",
        when_to_use="Precise lookups in structured catalogues/tables (prices, codes, quantities, lead times).",
        parameters={"type": "object", "properties": {
            "query": {"type": "string", "description": "keywords, ID or name to search for"},
            "column": {"type": "string", "description": "optional column name to restrict the search"},
        }, "required": ["query"]},
        fn=csv_lookup,
        prerequisite="knowledge folder contains at least one CSV/TSV file",
        signals=("catalog", "catalogue", "part", "price", "stock", "inventory", "sku", "table", "csv", "lookup", "list", "code"),
    ),
    "calculator": Tool(
        name="calculator",
        description="Evaluate an arithmetic expression exactly, e.g. '12 * 45.5 * 0.9'. Use for totals, discounts, conversions, pro-rating.",
        when_to_use="The agent must compute numbers (totals, discounts, pro-rata entitlements, conversions).",
        parameters={"type": "object", "properties": {"expression": {"type": "string", "description": "arithmetic expression"}}, "required": ["expression"]},
        fn=calculator,
        prerequisite="requirements involve computing quantities, costs, totals, entitlements or conversions",
        signals=("calculat", "total", "cost", "quote", "discount", "sum", "how much", "compute", "pro-rat", "prorat", "estimate", "convert", "budget"),
    ),
    "weather_forecast": Tool(
        name="weather_forecast",
        description="Get the live weather forecast (temperature, precipitation, wind) for a named place via the public open-meteo API.",
        when_to_use="Questions about current/forecast weather or sea/port conditions at a location.",
        parameters={"type": "object", "properties": {
            "location": {"type": "string", "description": "city or port name"},
            "days": {"type": "integer", "description": "forecast days 1-7"},
        }, "required": ["location"]},
        fn=weather_forecast,
        prerequisite="requirements explicitly involve weather, wind, forecast or sea/port conditions",
        signals=("weather", "forecast", "wind", "rain", "storm", "temperature", "sea state", "conditions at", "climate"),
    ),
    "current_date": Tool(
        name="current_date",
        description="Return today's date and weekday. Use for deadlines, notice periods, 'how many days until', expiry or delivery date questions.",
        when_to_use="Answers depend on today's date (deadlines, elapsed time, delivery ETAs, eligibility windows).",
        parameters={"type": "object", "properties": {}},
        fn=current_date,
        prerequisite="requirements involve deadlines, dates, elapsed time or scheduling relative to today",
        signals=("today", "deadline", "days until", "due date", "expir", "eta ", "deliver by", "how long ago", "current date", "this week", "overdue"),
    ),
}


def run_tool(name: str, args: dict | str) -> dict:
    if name not in REGISTRY:
        return {"error": f"unknown tool {name}"}
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except Exception:
            args = {"query": args, "expression": args, "location": args}
    params = REGISTRY[name].parameters.get("properties", {})
    clean = {k: v for k, v in (args or {}).items() if k in params}
    try:
        return REGISTRY[name].fn(**clean)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
