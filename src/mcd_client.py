#!/usr/bin/env python3
"""
mcd-film-scout · 麦当劳 MCP 客户端
================================
封装麦当劳 MCP Server（https://mcp.mcd.cn）的 Streamable HTTP 接入，
供本项目的 Skill 调用。

安全约定：
  · Token 只从环境变量 MCD_MCP_TOKEN 读取，绝不写入源码或配置文件
  · 只封装本项目实际用到的工具，不做全量透传

作者：孟波（mengboqingdao）  |  用 WorkBuddy 开发
"""
import json
import os
import re
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

MCP_ENDPOINT = os.environ.get("MCD_MCP_URL", "https://mcp.mcd.cn")
TOKEN_ENV = "MCD_MCP_TOKEN"

# 本项目实际调用的工具白名单
# ★ 名称与参数均以 MCP Server 1.0.9 的 tools/list 实际返回为准
TOOL_WHITELIST = (
    "campaign-calendar",          # 活动日历：查当月营销活动
    "now-time-info",              # 当前时间：判断活动是否在进行中
    "mall-points-products",       # 积分商城商品：主题活动 spuId 的来源
    "query-party-city",           # 主题活动可参与城市（需 spuId）
    "query-party-store",          # 主题活动门店（需城市 code + spuId）
    "query-party-store-date",     # 门店可约日期（需 spuId + storeCode）
    "query-party-store-session",  # 指定日期可约场次（需 spuId + storeCode + dateStr）
    "query-nearby-stores",        # 附近门店（需 beType + searchType）
    "query-meals",                # 当前门店在售餐品（需 storeCode + orderType + beType）
    "list-nutrition-foods",       # 餐品营养成分
    "query-store-coupons",        # 门店可用优惠券（需 storeCode + orderType + beType）
    "available-coupons",          # 可领取的麦麦省券
    "query-my-account",           # 积分账户
)


class McdMcpError(RuntimeError):
    """MCP 调用失败。"""


class McdClient:
    """麦当劳 MCP Server 最小客户端。

    只做三件事：初始化会话、列出工具、调用工具。
    """

    def __init__(self, token: Optional[str] = None, endpoint: str = MCP_ENDPOINT):
        self.token = token or os.environ.get(TOKEN_ENV, "")
        if not self.token:
            raise McdMcpError(
                f"未找到 MCP Token。请设置环境变量 {TOKEN_ENV}，"
                f"Token 申请地址：https://open.mcd.cn/mcp"
            )
        self.endpoint = endpoint
        self._session_id: Optional[str] = None
        self._id = 0
        self._tools: Optional[List[Dict[str, Any]]] = None

    # ── 底层 HTTP ────────────────────────────────────────────────
    def _headers(self) -> Dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
            "MCP-Protocol-Version": "2024-11-05",
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code == 401:
                raise McdMcpError("MCP Token 无效或已过期（401），请重新申请。") from e
            if e.code == 429:
                raise McdMcpError("触发限流（429），Token 每分钟上限 600 次，请稍后重试。") from e
            raise McdMcpError(f"MCP HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise McdMcpError(f"无法连接麦当劳 MCP：{e.reason}") from e

        # Streamable HTTP 可能返回 SSE 格式
        if raw.lstrip().startswith("event:") or raw.lstrip().startswith("data:"):
            for line in raw.splitlines():
                if line.startswith("data:"):
                    raw = line[5:].strip()
                    break
        data = json.loads(raw)
        if "error" in data:
            err = data["error"]
            raise McdMcpError(f"MCP 返回错误：{err.get('message', err)}")
        return data.get("result", {})

    # ── 高层 API ────────────────────────────────────────────────
    def initialize(self) -> Dict[str, Any]:
        """建立会话。必须先调用一次。"""
        return self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcd-film-scout", "version": "1.0.0"},
        })

    def list_tools(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """获取服务端工具清单（本项目只关心白名单内的）。"""
        if self._tools is not None and not refresh:
            return self._tools
        self.initialize()
        res = self._rpc("tools/list", {})
        tools = res.get("tools", [])
        self._tools = [t for t in tools if t.get("name") in TOOL_WHITELIST]
        return self._tools

    def call(self, tool: str, args: Optional[Dict[str, Any]] = None) -> Any:
        """调用一个工具。tool 必须在白名单内。

        ★ MCP Server 1.0.9 的返回有两种形态：
          ① 纯 JSON 字符串
          ② 「字段说明 + ## Original Response + JSON」的 Markdown 文本
          （例如 campaign-calendar、available-coupons、list-nutrition-foods）
        这里统一把 ② 里的 JSON 抽出来，解析失败时原样返回文本。
        """
        if tool not in TOOL_WHITELIST:
            raise McdMcpError(f"工具 {tool} 不在本项目白名单内，拒绝调用。")
        if self._tools is None:
            self.list_tools()
        res = self._rpc("tools/call", {
            "name": tool,
            "arguments": args or {},
        })
        # MCP 工具返回一般为 content 数组
        content = res.get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        if not texts:
            return res
        raw = "\n".join(texts)
        return parse_tool_output(raw)


# ── 返回值解析 ────────────────────────────────────────────────────
_ORIGINAL_RE = re.compile(r"##\s*Original Response\s*\n+(.*)", re.S)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n+(.*?)```", re.S)


def parse_tool_output(raw: str) -> Any:
    """从 MCP 工具返回文本中抽出结构化数据。

    优先找 `## Original Response` 后面的 JSON；
    找不到就找整段文本里的第一个 JSON 对象/数组；
    都没有则原样返回文本。
    """
    if not isinstance(raw, str):
        return raw

    candidates: List[str] = []
    m = _ORIGINAL_RE.search(raw)
    if m:
        candidates.append(m.group(1).strip())
    m2 = _JSON_BLOCK_RE.search(raw)
    if m2:
        candidates.append(m2.group(1).strip())
    candidates.append(raw.strip())

    for c in candidates:
        if not c:
            continue
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        # obj 解析成功，但 data 可能还是字符串（两种情况）
        inner = obj.get("data") if isinstance(obj, dict) else None
        if isinstance(inner, str):
            try:
                obj["data"] = json.loads(inner)
                return obj
            except json.JSONDecodeError:
                # list-nutrition-foods 返回的是自定义文本格式：
                #   [160]{productName,energyKcal,protein,...}:
                #     猪柳麦满分,null,1288,308,16,...
                parsed = parse_table_text(inner)
                if parsed:
                    obj["data"] = parsed
                    return obj
        return obj
    return raw


_TABLE_HEADER_RE = re.compile(r"^\[(\d+)\]\s*\{([^}]*)\}\s*:\s*$")


def parse_table_text(text: str) -> List[Dict[str, Any]]:
    """解析 MCP 的自定义表格文本格式。

    形如：
        [160]{productName,nutritionDescription,energyKcal,protein}:
          猪柳麦满分,null,308,16
          猪柳蛋麦满分,null,387,23
    返回 [{'productName': '猪柳麦满分', 'energyKcal': '308', ...}, ...]
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    m = _TABLE_HEADER_RE.match(lines[0].strip())
    if not m:
        return []
    cols = [c.strip() for c in m.group(2).split(",")]
    rows: List[Dict[str, Any]] = []
    for ln in lines[1:]:
        parts = [p.strip() for p in ln.strip().split(",")]
        if len(parts) < len(cols):
            parts += [""] * (len(cols) - len(parts))
        row: Dict[str, Any] = {}
        for i, c in enumerate(cols):
            v = parts[i]
            if v in ("null", "None", ""):
                row[c] = None
            else:
                try:
                    row[c] = float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) else v
                except ValueError:
                    row[c] = v
        rows.append(row)
    return rows
