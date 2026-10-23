#!/usr/bin/env python3
"""
demo_client.py · 离线演示模式
================================
让访客在没有 MCP Token 的情况下也能跑出完整场记板，
从而看懂这个项目到底产出什么。

★ 重要：这里的示例数据是【样例】，不是真实数据。
  真实数据必须来自一次真实的 MCP 调用。
  演示模式下的输出会明确标注「演示数据」。
  这与项目「宁可空手，也不编造」的原则不冲突——
  因为它压根不假装那是真的。

作者：孟波（mengboqingdao）  |  用 WorkBuddy 开发
"""
from typing import Any, Dict, List
from mcd_client import McdClient, McdMcpError, TOOL_WHITELIST


# ── 演示用的样例数据（全部标注为样例） ──────────────────────────
_DEMO_CALENDAR = {
    "code": 0,
    "data": {
        "list": [
            {"activityName": "麦麦月圆夜·主题夜场", "status": 1},
            {"activityName": "开学季·学生早餐周", "status": 1},
            {"activityName": "秋日热饮第二杯半价", "status": 0},
        ]
    },
}

_DEMO_CITIES = {
    "code": 0,
    "data": {"list": [
        {"cityName": "青岛"}, {"cityName": "北京"}, {"cityName": "上海"},
        {"cityName": "杭州"}, {"cityName": "成都"},
    ]},
}

_DEMO_STORES = {
    "code": 0,
    "data": {"list": [
        {"storeName": "崂山金家岭店"},
        {"storeName": "市南香港中路店"},
        {"storeName": "李沧万达店"},
    ]},
}

_DEMO_SESSIONS = {
    "code": 0,
    "data": {"list": [
        {"sessionTime": "19:00-20:30", "remainNum": 6},
        {"sessionTime": "20:30-22:00", "remainNum": 2},
    ]},
}

_DEMO_MEALS = {
    "code": 0,
    "data": {"list": [
        {"mealName": "麦麦月圆套餐", "price": 39.0},
        {"mealName": "月圆主题双人餐", "price": 68.0},
        {"mealName": "热拿铁（中）", "price": 18.0},
        {"mealName": "黄金薯条（中）", "price": 11.0},
        {"mealName": "鸡翅包饭", "price": 24.0},
    ]},
}

_DEMO_NUTRITION = {
    "code": 0,
    "data": {"list": [
        {"name": "麦麦月圆套餐", "calories": 780, "protein": 32},
        {"name": "热拿铁（中）", "calories": 145, "protein": 6},
        {"name": "鸡翅包饭", "calories": 520, "protein": 24},
        {"name": "黄金薯条（中）", "calories": 330, "protein": 4},
    ]},
}

_DEMO_COUPONS = {
    "code": 0,
    "data": {"list": [
        {"couponName": "第二份半价券", "amount": 5.0},
        {"couponName": "满50减12券", "amount": 12.0},
        {"couponName": "9元咖啡券", "amount": 9.0},
    ]},
}

_DEMO_NEARBY = _DEMO_STORES

_DEMO_MAP = {
    "campaign-calendar": _DEMO_CALENDAR,
    "query-party-city": _DEMO_CITIES,
    "query-party-store": _DEMO_STORES,
    "query-partystore-date": _DEMO_SESSIONS,
    "query-partystore-session": _DEMO_SESSIONS,
    "query-nearby-stores": _DEMO_NEARBY,
    "query-meals": _DEMO_MEALS,
    "query-meal-detail": _DEMO_MEALS,
    "list-nutrition-foods": _DEMO_NUTRITION,
    "query-store-coupons": _DEMO_COUPONS,
    "available-coupons": _DEMO_COUPONS,
    "query-meal-assistance": {"code": 0, "data": {"list": []}},
}


class DemoClient(McdClient):
    """离线演示客户端：接口签名与真实客户端一致，但不发起网络请求。

    只用于让人看懂输出格式，产出的内容一律带「演示数据」标记。
    """

    def __init__(self, city: str = "青岛"):
        # 故意不调 super().__init__，避免要求 Token
        self.endpoint = "demo://local"
        self.token = "demo"
        self._session_id = None
        self._id = 0
        self._tools = None
        self.city = city
        self.called: List[str] = []

    def initialize(self) -> Dict[str, Any]:
        return {"protocolVersion": "2024-11-05", "serverInfo": {"name": "demo"}}

    def list_tools(self, refresh: bool = False) -> List[Dict[str, Any]]:
        if self._tools is None:
            self._tools = [{"name": n} for n in sorted(_DEMO_MAP)]
        return self._tools

    def call(self, tool: str, args: Any = None) -> Any:
        if tool not in TOOL_WHITELIST:
            raise McdMcpError(f"工具 {tool} 不在本项目白名单内，拒绝调用。")
        self.called.append(tool)
        if tool not in _DEMO_MAP:
            raise McdMcpError(f"演示模式未覆盖工具 {tool}")
        return _DEMO_MAP[tool]


if __name__ == "__main__":
    c = DemoClient()
    print("演示客户端可用工具：", len(c.list_tools()))
    print("示例查询：", c.call("query-party-city"))
