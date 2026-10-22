#!/usr/bin/env python3
"""
film_scout.py · 麦门场记板核心
================================
把麦当劳 MCP 的「活动 / 门店 / 场次 / 菜单 / 营养」数据，
翻译成一份**拍摄场记板**：去哪、什么时候、拍什么、怎么拍、顺带吃什么。

设计原则：
  1. 只读——不下单、不支付、不改账户
  2. 每条建议都必须能溯源到具体的一次 MCP 调用
  3. MCP 不可用时降级为「离线提示」，不编造数据

作者：孟波（mengboqingdao）  |  用 WorkBuddy 开发
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcd_client import McdClient, McdMcpError  # noqa: E402


# ══════════════════════════════════════════════════════════════
#  数据结构
# ══════════════════════════════════════════════════════════════

@dataclass
class ShotPlan:
    """一个拍摄预案。"""
    theme: str                      # 主题（来自活动名）
    subject: str                    # 拍什么
    composition: List[str]          # 构图方案
    light: List[str]                # 光线方案
    color: List[str]                # 色彩参考（来自主题餐品）
    props: List[str]                # 画面道具
    gear: Dict[str, str]            # 器材建议
    source_tools: List[str] = field(default_factory=list)  # 溯源

    def to_markdown(self) -> str:
        L = []
        L.append(f"## 拍摄预案：{self.theme}\n")
        L.append(f"**拍什么**：{self.subject}\n")
        L.append("**构图**")
        for c in self.composition:
            L.append(f"- {c}")
        L.append("\n**光线**")
        for c in self.light:
            L.append(f"- {c}")
        L.append("\n**色彩参考**（来自店内实际在售主题餐品）")
        for c in self.color:
            L.append(f"- {c}")
        if self.props:
            L.append("\n**画面道具**")
            for c in self.props:
                L.append(f"- {c}")
        L.append("\n**器材**")
        for k, v in self.gear.items():
            L.append(f"- {k}：{v}")
        L.append(f"\n<sub>数据来源：{'、'.join(self.source_tools)}</sub>")
        return "\n".join(L)


@dataclass
class FieldNote:
    """一份完整的场记板。"""
    city: str
    store: str
    activity: str
    dates: List[str] = field(default_factory=list)
    sessions: List[str] = field(default_factory=list)
    plan: Optional[ShotPlan] = None
    meals: List[str] = field(default_factory=list)
    nutrition: List[str] = field(default_factory=list)
    coupons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        L = [f"# 麦门场记板 · {self.activity}", ""]
        L.append(f"**城市**：{self.city}　|　**门店**：{self.store}\n")
        if self.dates:
            L.append(f"**可约日期**：{'、'.join(self.dates)}")
        if self.sessions:
            L.append(f"**可约场次**：{'、'.join(self.sessions)}\n")
        if self.plan:
            L.append(self.plan.to_markdown())
        if self.meals:
            L.append("\n## 当天能点到的餐品\n")
            L += [f"- {m}" for m in self.meals]
        if self.nutrition:
            L.append("\n## 拍摄间隙补给参考\n")
            L += [f"- {n}" for n in self.nutrition]
        if self.coupons:
            L.append("\n## 可用优惠券\n")
            L += [f"- {c}" for c in self.coupons]
        if self.warnings:
            L.append("\n## 注意事项\n")
            L += [f"- {w}" for w in self.warnings]
        L.append(f"\n<sub>调用工具：{'、'.join(self.tools_used) or '无'}</sub>")
        L.append("\n> 本场记板由麦门场记板生成，餐品信息与价格以麦当劳官方渠道实时结果为准。")
        return "\n".join(L)


# ══════════════════════════════════════════════════════════════
#  取数：把 MCP 返回的异构结构压成可用的列表
# ══════════════════════════════════════════════════════════════

def _walk(node: Any):
    """递归遍历任意嵌套结构，产出所有 dict。"""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def pick(d: Dict[str, Any], *names: str) -> Optional[Any]:
    """从 dict 里按候选键名取值，兼容各种字段命名习惯。"""
    for n in names:
        if n in d and d[n] not in (None, "", []):
            return d[n]
    return None


def extract_items(raw: Any) -> List[Dict[str, Any]]:
    """从 MCP 返回里抽出「记录列表」。取最长的那个数组作为主列表。"""
    best: List[Any] = []
    for d in _walk(raw):
        for v in d.values():
            if isinstance(v, list) and len(v) > len(best):
                if any(isinstance(x, dict) for x in v):
                    best = v
    return [x for x in best if isinstance(x, dict)]


def extract_names(raw: Any, *keys: str) -> List[str]:
    """从记录列表里按候选字段名抽出可读名称。"""
    out: List[str] = []
    for d in extract_items(raw):
        for k in keys:
            v = pick(d, k)
            if v and isinstance(v, (str, int, float)):
                out.append(str(v))
                break
    return out


# ══════════════════════════════════════════════════════════════
#  核心：生成拍摄预案
# ══════════════════════════════════════════════════════════════

# 主题配色关键词 → 摄影用词映射。
# 把「餐品名字里的颜色词」翻译成「画面里能抓到的颜色」。
COLOR_WORDS = {
    "红": "麦当劳标志性的红与灯箱暖光，做画面主色",
    "黄": "金黄薯条与灯光的暖黄，适合做前景与引导线",
    "金": "金色包装的反射光，拍饮料与甜品时当高光用",
    "绿": "沙拉与蔬菜的青绿，压住暖调的燥",
    "白": "餐盘与杯身的白，做高键与负空间",
    "黑": "深色桌面与暗背景，衬托亮部食物",
    "紫": "葡萄与紫薯的紫，适合做冷调对比",
    "橙": "橙味饮品与橙黄灯光的过渡色",
}

# 场景关键词 → 构图方案
COMPOSITION_RULES = [
    (r"派对|聚会|生日|亲子", [
        "多人互动用一个中心人物 + 环状视线，蛋糕切开的瞬间抓表情",
        "低机位贴近桌面，让气球与吊饰从画面上沿入画",
        "俯拍桌面全景，把所有道具排成一条对角线",
    ]),
    (r"品鉴|美食|新品|试吃|餐厅", [
        "45° 俯角主图，把餐盘放在三分线交点，留出前景虚化",
        "手部动作特写：拿起、掰开、倒酱的瞬间比静态摆盘有生气",
        "平视贴桌面拍，用桌面反光做倒影增加层次",
    ]),
    (r"亲子|儿童|小朋友", [
        "蹲到孩子视线高度平拍，背景压到只剩色块",
        "抓眼神与手的互动，构图留出视线方向的空间",
    ]),
    (r"夜|晚|灯|节|圣诞|新年", [
        "用店外灯箱与霓虹做背景光，人物做剪影",
        "长曝光 1/15 秒以上，把来往人流拉成连续光带",
        "靠窗位置向外拍，用玻璃反射做双重画面",
    ]),
]

# 默认构图（没匹配到主题时）
COMPOSITION_DEFAULT = [
    "主图用三分法，主体放在右三分线，留白给店招文字",
    "低机位与桌面同高，强调纵深与现场感",
    "抓拍而非摆拍：等动作发生的那一刹那按快门",
]

# 场景关键词 → 光线方案
LIGHT_RULES = [
    (r"夜|晚|灯|节|圣诞|新年", [
        "以店内暖光为主光，关闭自动白平衡保留暖调",
        "用手机手电或小反光板给主体补一点眼神光",
    ]),
    (r"上午|早餐|早", [
        "用窗边自然光做侧逆光，注意别让玻璃反光进镜头",
        "曝光以窗光为准，室内暗部可欠曝半档保住氛围",
    ]),
]

LIGHT_DEFAULT = [
    "以窗光或店内顶光为主，避免顶光在脸上留下硬阴影",
    "让主体面向光源或侧 45°，轮廓更有立体感",
]


def build_plan(activity_name: str, meals: List[str],
                tools: List[str]) -> ShotPlan:
    """根据活动名与在售餐品，生成一份拍摄预案。"""
    plan = ShotPlan(
        theme=activity_name,
        subject=f"以「{activity_name}」的现场氛围与在售餐品为主体，把活动本身当作一次街头纪实",
        composition=[],
        light=[],
        color=[],
        props=[],
        gear={
            "机身": "任意可手动曝光的相机或手机专业模式",
            "焦段": "35–50mm 拍环境与人物，85–200mm 拍细节与虚化",
            "快门": "环境 1/60 秒以上保持稳定；想拉人流光带可用 1/15 秒并上脚架",
            "白平衡": "固定为 4000K 左右，拍摄现场时避免自动跳色",
        },
        source_tools=list(tools),
    )

    for pat, opts in COMPOSITION_RULES:
        if re.search(pat, activity_name):
            plan.composition = list(opts)
            break
    if not plan.composition:
        plan.composition = list(COMPOSITION_DEFAULT)

    for pat, opts in LIGHT_RULES:
        if re.search(pat, activity_name):
            plan.light = list(opts)
            break
    if not plan.light:
        plan.light = list(LIGHT_DEFAULT)

    # 色彩：从餐品名里找颜色词
    seen = set()
    for m in meals:
        for word, advice in COLOR_WORDS.items():
            if word in m and word not in seen:
                seen.add(word)
                plan.color.append(f"{advice}（对应「{m}」）")
    if not plan.color:
        plan.color = [
            "以店内的整体色调为基准，先看主光源色温再决定怎么配",
            "拍食物时用白盘或白杯做参照，白平衡才不会跑偏",
        ]

    # 道具：餐品里出现的可拍摄物
    prop_words = {
        "薯条": "薯条盒的金属反光是很好的前景",
        "汉堡": "汉堡的横截面最能出层次，切面朝镜头",
        "可乐": "杯壁冷凝水珠拍特写，显新鲜",
        "咖啡": "拉花做俯拍，几何形状很上镜",
        "蛋挞": "蛋挞表面的焦斑，微距拍细节",
        "甜筒": "甜筒的螺旋线条，适合慢速快门转出旋转感",
        "蛋糕": "切开的瞬间，奶油的分层最动人",
    }
    for m in meals:
        for p, desc in prop_words.items():
            if p in m:
                plan.props.append(desc)
    plan.props = list(dict.fromkeys(plan.props))[:4]

    return plan


def nutrition_advice(nutrition_raw: Any, minutes: int = 120) -> List[str]:
    """从营养数据里给拍摄间歇的补给建议。"""
    items = extract_items(nutrition_raw)
    out = []
    for d in items:
        name = pick(d, "name", "foodName", "餐品名称", "title")
        kcal = pick(d, "energy", "calories", "kcal", "热量", "energyKcal")
        protein = pick(d, "protein", "蛋白质")
        if not name:
            continue
        if kcal is None:
            continue
        try:
            k = float(kcal)
        except (TypeError, ValueError):
            continue
        if k <= 400:
            tip = "轻量档，适合不想影响状态时垫一口"
        elif k <= 700:
            tip = "主食档，能量够撑住一段连续拍摄"
        else:
            tip = "重档，吃完会有明显的倦意，重要场次慎选"
        extra = f"，蛋白质 {protein}g" if protein is not None else ""
        out.append(f"{name}：约 {int(k)} 千卡{extra} —— {tip}")
    if not out:
        out = ["营养数据暂不可用，出门前先吃点东西，拍摄间隙别硬撑"]
    return out[:6]


# ══════════════════════════════════════════════════════════════
#  对外主流程
# ══════════════════════════════════════════════════════════════

def scout(city: str, client: Optional[McdClient] = None,
          store_hint: str = "") -> FieldNote:
    """主流程：生成一份场记板。

    client 为 None 时只返回离线提示，不编造任何数据。
    """
    note = FieldNote(city=city, store=store_hint or "（待定）", activity="（待定）")

    if client is None:
        note.warnings.append(
            "未配置 MCP Token，无法获取实时活动与门店数据。"
            "请到 https://open.mcd.cn/mcp 申请 Token，"
            "并设置环境变量 MCD_MCP_TOKEN 后重试。"
        )
        note.warnings.append(
            "本工具不内置任何活动/菜单/价格数据——宁可空手，也不编造。"
        )
        return note

    used: List[str] = []

    # 1) 活动日历
    try:
        cal = client.call("campaign-calendar", {})
        used.append("campaign-calendar")
        acts = extract_items(cal)
        names = [str(pick(a, "name", "activityName", "title", "活动名称", "campaignName"))
                 for a in acts]
        names = [n for n in names if n and n != "None"]
        note.activity = names[0] if names else "当月营销活动"
        if names:
            note.warnings.append(f"本月活动共 {len(names)} 项：" + "、".join(names[:6]))
    except McdMcpError as e:
        note.warnings.append(f"活动日历查询失败：{e}")

    # 2) 主题活动可参与城市
    try:
        cities = client.call("query-party-city", {})
        used.append("query-party-city")
        cs = extract_names(cities, "cityName", "name", "城市名称", "city")
        if cs:
            note.warnings.append(
                f"主题活动可参与城市（{len(cs)} 个）：" + "、".join(cs[:12])
                + ("　※ 你所在的 " + city + (" 在其中。" if city in cs else " 不在其中。"))
            )
    except McdMcpError as e:
        note.warnings.append(f"主题活动城市查询失败：{e}")

    # 3) 门店
    try:
        if store_hint:
            stores = client.call("query-party-store", {"cityName": city})
            used.append("query-party-store")
            sn = extract_names(stores, "storeName", "name", "门店名称", "store")
            if sn:
                note.store = sn[0]
        else:
            near = client.call("query-nearby-stores", {"latitude": "", "longitude": ""})
            used.append("query-nearby-stores")
            nn = extract_names(near, "storeName", "name", "门店名称")
            if nn:
                note.store = nn[0]
    except McdMcpError as e:
        note.warnings.append(f"门店查询失败：{e}")

    # 4) 菜单与餐品
    meals: List[str] = []
    try:
        m = client.call("query-meals", {})
        used.append("query-meals")
        meals = extract_names(m, "mealName", "name", "餐品名称", "productName")
        note.meals = meals[:12]
    except McdMcpError as e:
        note.warnings.append(f"菜单查询失败：{e}")

    # 5) 营养
    try:
        n = client.call("list-nutrition-foods", {})
        used.append("list-nutrition-foods")
        note.nutrition = nutrition_advice(n)
    except McdMcpError as e:
        note.nutrition = ["营养数据暂不可用"]

    # 6) 券
    try:
        c = client.call("available-coupons", {})
        used.append("available-coupons")
        cn = extract_names(c, "couponName", "name", "券名称", "title", "desc")
        note.coupons = [x for x in cn if x][:5]
    except McdMcpError as e:
        note.warnings.append(f"优惠券查询失败：{e}")

    # 7) 生成拍摄预案
    note.plan = build_plan(note.activity, note.meals, used)

    note.tools_used = used
    if not note.dates and not note.sessions:
        note.warnings.append(
            "档期（可约日期与场次）需要具体门店后再查："
            "在对话里指定门店名，我会接着调 query-partystore-date 与 query-partystore-session。"
        )
    return note


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="麦门场记板 · 生成拍摄场记板")
    ap.add_argument("--city", default="青岛", help="城市名")
    ap.add_argument("--store", default="", help="指定门店名（指定后才会查档期）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    try:
        client = McdClient()
    except McdMcpError as e:
        print(f"[离线模式] {e}\n", file=sys.stderr)
        client = None

    note = scout(args.city, client, args.store)
    if args.json:
        print(json.dumps(asdict(note), ensure_ascii=False, indent=2))
    else:
        print(note.to_markdown())


if __name__ == "__main__":
    main()
