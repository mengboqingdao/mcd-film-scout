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

★ 样例数据的结构严格照抄真实 MCP 返回的字段名（spuId / code /
  storeCode / timeStart / leftNum / categories[].meals[] 等），
  这样演示模式走的是和真实模式**同一条代码路径**，
  不会出现「演示能跑、真实跑不通」的假通过。

作者：孟波（mengboqingdao）  |  用 WorkBuddy 开发
"""
from typing import Any, Dict, List
from mcd_client import McdClient, McdMcpError, TOOL_WHITELIST


# ── 演示用的样例数据（全部标注为样例） ──────────────────────────
# 活动日历
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

# 主题活动的 spuId（query-party-city / -store / -date 的必填参数来源）
_DEMO_PRODUCTS = {
    "code": 0,
    "data": {
        "list": [
            {"spuId": 1779, "spuName": "麦麦生日派对"},
            {"spuId": 1830, "spuName": "亲子读书会"},
        ]
    },
}

# 可参与城市
_DEMO_CITIES = {
    "code": 0,
    "data": {"list": [
        {"code": "370200", "name": "青岛"},
        {"code": "110100", "name": "北京"},
        {"code": "310100", "name": "上海"},
        {"code": "330100", "name": "杭州"},
        {"code": "510100", "name": "成都"},
    ]},
}

# 参与门店
_DEMO_STORES = {
    "code": 0,
    "data": {"list": [
        {"code": "3350001", "name": "佳世客餐厅", "distanceText": "1.2km"},
        {"code": "3350002", "name": "香港中路餐厅", "distanceText": "3.4km"},
        {"code": "3350003", "name": "李沧万达餐厅", "distanceText": "8.6km"},
    ]},
}

# 可约日期
_DEMO_DATES = {
    "code": 0,
    "data": {"list": [
        {"date": "2026-10-26"}, {"date": "2026-10-27"}, {"date": "2026-10-28"},
        {"date": "2026-10-29"}, {"date": "2026-10-30"}, {"date": "2026-10-31"},
        {"date": "2026-11-01"},
    ]},
}

# 场次与余位
_DEMO_SESSIONS = {
    "code": 0,
    "data": {"list": [
        {"timeStart": "12:00", "timeEnd": "13:30", "leftNum": 12},
        {"timeStart": "18:30", "timeEnd": "20:00", "leftNum": 12},
    ]},
}

# 菜单：真实结构是 data.categories[].meals[]，且 meals 里只有 code 与 tags
_DEMO_MEALS = {
    "code": 0,
    "data": {"categories": [
        {"name": "人气热卖", "meals": [
            {"code": "m1001", "tags": ["心形薯饼同款比心"]},
            {"code": "m1002", "tags": ["黄金薯条"]},
        ]},
        {"name": "鸡肉汉堡/卷", "meals": [
            {"code": "m2001", "tags": ["麦辣鸡腿堡"]},
            {"code": "m2002", "tags": ["板烧鸡腿堡"]},
        ]},
        {"name": "咖啡与饮品", "meals": [
            {"code": "m3001", "tags": ["热拿铁"]},
            {"code": "m3002", "tags": ["可口可乐"]},
            {"code": "m3003", "tags": ["橙汁"]},
        ]},
        {"name": "甜品", "meals": [
            {"code": "m4001", "tags": ["蛋挞"]},
            {"code": "m4002", "tags": ["甜筒"]},
            {"code": "m4003", "tags": ["红豆派"]},
        ]},
        {"name": "主食", "meals": [
            {"code": "m5001", "tags": ["鸡翅包饭"]},
            {"code": "m5002", "tags": ["麦麦月圆套餐"]},
        ]},
    ]},
}

# 营养：真实结构是扁平列表，字段名为 productName / energyKcal / protein
_DEMO_NUTRITION = {
    "code": 0,
    "data": {"list": [
        {"productName": "麦麦月圆套餐", "energyKcal": 780, "protein": 32},
        {"productName": "热拿铁（中）", "energyKcal": 145, "protein": 6},
        {"productName": "鸡翅包饭", "energyKcal": 520, "protein": 24},
        {"productName": "黄金薯条（中）", "energyKcal": 330, "protein": 4},
        {"productName": "蛋挞", "energyKcal": 190, "protein": 3},
    ]},
}

# 券
_DEMO_COUPONS = {
    "code": 0,
    "data": {"list": [
        {"couponName": "第二份半价券"},
        {"couponName": "满50减12券"},
        {"couponName": "9元咖啡券"},
    ]},
}

_DEMO_EMPTY = {"code": 0, "data": {"list": []}}

# 工具名 → 样例数据
# ★ 注意：既登记真实工具名（query-party-store-date），
#   也登记旧文档里的错误写法（query-partystore-date），
#   万一有人照旧文档改了代码，演示模式也不至于直接崩。
_DEMO_MAP = {
    "campaign-calendar": _DEMO_CALENDAR,
    "now-time-info": {"code": 0, "data": {"currentTime": "2026-10-23 10:50:00"}},
    "mall-points-products": _DEMO_PRODUCTS,
    "query-party-city": _DEMO_CITIES,
    "query-party-store": _DEMO_STORES,
    "query-party-store-date": _DEMO_DATES,
    "query-party-store-session": _DEMO_SESSIONS,
    "query-partystore-date": _DEMO_DATES,
    "query-partystore-session": _DEMO_SESSIONS,
    "query-nearby-stores": _DEMO_STORES,
    "query-meals": _DEMO_MEALS,
    "query-meal-detail": _DEMO_MEALS,
    "list-nutrition-foods": _DEMO_NUTRITION,
    "query-store-coupons": _DEMO_COUPONS,
    "available-coupons": _DEMO_COUPONS,
    "query-meal-assistance": _DEMO_EMPTY,
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
