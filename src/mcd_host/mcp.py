"""麦当劳中国 MCP Server 只读客户端。

- 接入地址：https://mcp.mcd.cn（Streamable HTTP，地址写死，不可配置）
- Token 只从本机读取：环境变量 MCD_MCP_TOKEN，或配置文件
  （$XDG_CONFIG_HOME/mcd-mcp/token、~/.config/mcd-mcp/token）
- 只允许调用白名单内的只读 Tool；写操作（下单、取消、领券、兑换、抽奖等）
  一律不在此列，由使用 MCP 的 Agent/客户端在用户确认后自行完成。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from . import __version__

MCP_URL = "https://mcp.mcd.cn"

READ_TOOLS = (
    "query-nearby-stores",
    "query-meals",
    "query-meal-detail",
    "query-store-coupons",
    "query-my-coupons",
    "available-coupons",
    "list-nutrition-foods",
    "campaign-calendar",
    "now-time-info",
)


class MCPError(Exception):
    """MCP 调用失败。message 面向用户，可直接展示。"""


def _load_dotenv() -> dict:
    """读取当前目录 .env（不打印、不覆盖已有环境变量）。

    支持两种写法：
      MCD_MCP_TOKEN=xxx      # 标准 KEY=VALUE
      xxx                    # 用户直接粘贴的裸 Token（整文件只有一行、没有等号时）
    """
    values = {}
    path = os.path.join(os.getcwd(), ".env")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = [line.strip() for line in fh if line.strip() and not line.strip().startswith("#")]
    except OSError:
        return values
    pairs = [line for line in lines if "=" in line]
    for line in pairs:
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            values[key] = value
    if not pairs and len(lines) == 1 and " " not in lines[0]:
        values["MCD_MCP_TOKEN"] = lines[0]
    return values


def resolve_token() -> str:
    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if not token:
        token = _load_dotenv().get("MCD_MCP_TOKEN", "").strip()
    if token:
        return token
    candidates = []
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        candidates.append(os.path.join(xdg, "mcd-mcp", "token"))
    candidates.append(os.path.expanduser("~/.config/mcd-mcp/token"))
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                value = fh.read().strip()
            if value:
                return value
        except OSError:
            continue
    raise MCPError(
        "没有找到麦当劳 MCP Token。请到 https://open.mcd.cn/mcp 用手机号登录，"
        "在控制台「激活」并复制 Token，然后设置环境变量 MCD_MCP_TOKEN，"
        "或写入 ~/.config/mcd-mcp/token（chmod 600）。没有 Token 时可以用 --demo 体验。"
    )


class MCPClient:
    def __init__(self, token: str = None, timeout: int = 30):
        self.token = token if token is not None else resolve_token()
        self.timeout = timeout
        self._session_id = None
        self._initialized = False
        self._rpc_id = 0

    def _next_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = urllib.request.Request(MCP_URL, data=body, headers=headers, method="POST")
        raw = None
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    session_id = response.headers.get("Mcp-Session-Id")
                    if session_id:
                        self._session_id = session_id
                    raw = response.read().decode("utf-8", "replace")
                break
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")[:200]
                except Exception:
                    pass
                if exc.code == 401:
                    raise MCPError("MCP Token 无效或已过期（401），请去 open.mcd.cn/mcp 控制台重新激活。")
                if exc.code == 429:
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
                        continue
                    raise MCPError("触发 MCP 限流（429，每分钟最多 600 次请求），请稍后再试。")
                raise MCPError(f"MCP 请求失败（HTTP {exc.code}）：{detail}")
            except urllib.error.URLError as exc:
                # 瞬时网络/SSL 抖动：退避重试（只读调用，重试无副作用）
                last_error = exc
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise MCPError(f"连不上麦当劳 MCP Server：{exc.reason}")
        if raw is None:
            raise MCPError(f"连不上麦当劳 MCP Server：{last_error.reason if last_error else '未知错误'}")
        return self._parse_response(raw)

    @staticmethod
    def _parse_response(raw: str) -> dict:
        text = raw.strip()
        if text.startswith("event:") or text.startswith("data:"):
            # SSE：取最后一条完整 JSON
            last = None
            for line in text.splitlines():
                if line.startswith("data:"):
                    last = line[5:].strip()
            if last:
                text = last
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise MCPError(f"MCP 返回了无法解析的内容：{text[:200]}")

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        result = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "mcd-host", "version": __version__},
                },
            }
        )
        if "error" in result:
            raise MCPError(f"MCP initialize 失败：{result['error']}")
        self._initialized = True
        try:
            self._notify("notifications/initialized")
        except MCPError:
            pass  # 部分服务端不强制要求

    def _notify(self, method: str) -> None:
        body = json.dumps({"jsonrpc": "2.0", "method": method}, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = urllib.request.Request(MCP_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout):
                pass
        except Exception:
            pass

    def call_tool(self, name: str, arguments: dict) -> object:
        if name not in READ_TOOLS:
            raise MCPError(f"mcd-host 只调用只读工具，拒绝调用 {name}。")
        self._ensure_initialized()
        result = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if "error" in result:
            message = result["error"].get("message", str(result["error"]))
            raise MCPError(f"MCP 工具 {name} 调用失败：{message}")
        content = result.get("result", {}).get("content", [])
        texts = [part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"]
        parsed = []
        for text in texts:
            parsed.append(self._parse_tool_text(text))
        if len(parsed) == 1:
            return parsed[0]
        return parsed

    @staticmethod
    def _extract_json(text: str):
        """从「说明文字 + JSON」的文本里提取真正的 JSON 对象。

        MCP 的部分工具会先给一段 Markdown 说明（里面也有 {code} 之类的花括号），
        再附完整 JSON。用 raw_decode 逐个 '{' 尝试解析，取第一个带 data/success 的对象。
        """
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and ("data" in obj or "success" in obj):
                return obj
        return None

    @staticmethod
    def _parse_tool_text(text: str):
        """MCP 的 text 内容可能是纯 JSON，也可能是「说明文字 + JSON + 说明文字」，尽量提取 JSON。"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        extracted = MCPClient._extract_json(text)
        if extracted is not None:
            return extracted
        return text
