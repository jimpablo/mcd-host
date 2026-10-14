# MCP_INTEGRATION.md — mcd-host 如何真实使用麦当劳 MCP

> 麦当劳程序员节创意开发大赛 · 参赛项目文件
> 本文说明 mcd-host 实际使用的麦当劳 MCP Server、Tool、调用流程和业务价值。

## 1. 使用的 MCP Server

| 项 | 值 |
|---|---|
| Server | 麦当劳中国 MCP Server（官方） |
| 接入地址 | `https://mcp.mcd.cn`（Streamable HTTP，地址在 `src/mcd_host/mcp.py` 中写死，不可配置） |
| 鉴权 | 请求头 `Authorization: Bearer <MCP_MCP_TOKEN>` |
| Token 申请 | <https://open.mcd.cn/mcp>（手机号登录 → 控制台 → 激活） |
| Token 存放 | 本机环境变量 `MCD_MCP_TOKEN` / 当前目录 `.env` / `~/.config/mcd-mcp/token`，**不进入仓库** |
| 限流 | 官方限制 600 次/分钟；mcd-host 每条命令调用次数为个位数，不会触发 |

## 2. 使用的 Tool（全部只读）

| Tool | 用途 | 用在哪 |
|---|---|---|
| `query-nearby-stores` | 按城市 + 地标查附近门店 | `mcd-host fetch stores --city X --keyword Y` |
| `query-meals` | 查门店当前在售菜单（分类、餐品编码、价格） | `mcd-host fetch menu --store-code <code>` |
| `query-meal-detail` | 查套餐组成与可替换选项 | 规划套餐类方案时的补充信息 |
| `query-store-coupons` | 查当前门店可用优惠券 | `mcd-host fetch coupons` |
| `query-my-coupons` | 查我的优惠券 | 同上 |
| `available-coupons` | 查麦麦省可领的券 | 同上（仅展示，不代领） |
| `list-nutrition-foods` | 查餐品营养成分（能量等） | `mcd-host fetch nutrition`，用于人均热量估算 |
| `campaign-calendar` | 当月活动日历 | 方案附注（如活动日提醒） |
| `now-time-info` | 当前时间 | 预约场景下推算取餐时间 |

**写操作一律不调用**：`create-order`、`cancel-order`、`auto-bind-coupons`、`mall-create-order`、`draw-lottery`、`party-order-create`、`delivery-create-address` 等均不在白名单内（`MCPClient.call_tool` 会直接拒绝）。下单由使用方（Agent 的 MCP 客户端或用户本人）在**确认方案之后**自行完成，mcd-host 只负责把方案算好。

## 3. 调用流程（以 Agent 用法为例）

```text
用户：周六请 6 个同事吃饭，预算 300，有人不吃辣。
  │
  ├─ 1. query-nearby-stores(city, keyword)        → 选门店，拿 storeCode
  ├─ 2. query-meals(storeCode)                    → 菜单 JSON ─┐
  ├─ 3. query-store-coupons(storeCode)            → 门店券   ─┤
  ├─ 4. query-my-coupons()                        → 我的券   ─┤ 组装 request JSON
  ├─ 5. available-coupons()                       → 可领券   ─┤
  ├─ 6. list-nutrition-foods()                    → 营养数据 ─┘
  │
  ├─ 7. mcd-host plan --input request.json --json
  │      → { lines[], subtotal, coupon, payable, perPerson, caloriesPerPerson, warnings, rationale }
  │
  ├─ 8. mcd-host card --plan plan.json -o host.svg
  │      → 自包含 SVG 分享卡片（菜品/份数/金额/人均/券，无个人信息）
  │
  └─ 9. 用户确认方案 → 用户/Agent 在自己的 MCP 客户端里调用 create-order 下单并付款
```

命令行（无 Agent）用法把第 1–6 步换成 `mcd-host fetch ...` 子命令，流程完全相同。

## 4. 业务价值

| 痛点 | mcd-host 的做法 |
|---|---|
| 请客点菜选择困难 | 按人数/场合/预算自动凑桌：套餐优先、小食甜品共享、最多 3 种轮换 |
| 凑券凑满减心累 | 实时拉券，一单一张券规则下挑最省的；差多少够满减会明说 |
| 人均分摊算账烦 | 人均应付直接算好（向上取整到分），方案卡直接发群 |
| 忌口/热量顾虑 | 忌口关键词自动过滤；有营养数据时估算人均热量并预警 |
| 交给 Agent 不放心 | mcd-host 只读；写操作必须用户确认后由用户/客户端执行，方案先于下单 |

## 5. 金额与单位约定

- 所有金额单位为**分**（与 MCP 一致）：JSON 中的 `price`/`total`/`subtotal`/`payable`/`perPerson`/`threshold`/`value` 都是整数分，展示时除以 100；
- CLI 的 `--budget` 单位为元（如 `300` 表示 ¥300），内部自动转分；
- 热量单位为千卡（kcal）。

## 6. MCP 返回格式与解析

麦当劳 MCP 的 Tool 返回分几种形态，mcd-host 都做了归一化：

| 形态 | 工具 | 处理方式 |
|---|---|---|
| 「Markdown 说明 + JSON」 | query-nearby-stores、query-meals、query-store-coupons | `raw_decode` 逐个 `{` 尝试解析，提取说明文字里内嵌的完整 JSON |
| 纯 JSON | list-nutrition-foods（data 为对象时） | 直接解析 |
| 文本表格 `[N]{headers}:` + CSV 行 | list-nutrition-foods（data 为字符串时） | 按表头切分每行，映射 `productName`/`energyKcal` |
| Markdown 渲染列表 | query-my-coupons | 解析 `## 券名` + `**优惠**: ¥X`，与门店券 JSON 按券名合并 |

其他实现要点：

- 金额单位以工具而异：`query-meals` 的 `currentPrice` 是**元**的字符串（`"13.9"`），`calculate-price` 等是**分**的整数，mcd-host 按类型分别转换；
- 必填入参：`query-nearby-stores` 需要 `searchType=2` + `beType=1` + `city` + `keyword`；`query-meals` 需要 `storeCode` + `beType` + `orderType`；
- 菜单名与营养表名常有规格差异（「玉米杯」vs「大杯玉米杯」），用「精确 → 互相包含 → 去规格前缀」三级模糊匹配；
- 网络抖动（SSL EOF）按只读调用做退避重试；401/429 按官方错误码给出可操作提示。

## 7. 错误处理

- `401`：Token 无效/过期 → 提示去 open.mcd.cn/mcp 控制台重新激活；
- `429`：触发限流 → 提示稍后重试；
- 其他网络/解析错误 → 原样转告，不静默重试；
- 菜单里没有价格的餐品会被跳过（MCP 的 `query-meals` 在部分餐品上可能不返回价格）。
