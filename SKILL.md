---
name: mcd-host
description: 麦门东道主 · 请客参谋：请客/团餐/团建/聚餐点麦当劳时，用本地命令行 mcd-host（mcd-host --json）基于麦当劳中国 MCP 凑一桌、挑最省的券、算人均和热量，并生成可分享的请客方案卡。用户提到请客、团餐、团建、聚餐、点麦当劳、麦当劳套餐怎么点、AA 算账时使用。只读：mcd-host 不调用任何 MCP 写工具，下单/取消/领券必须先把方案和确认摘要给用户看，用户明确同意后才由用户或 Agent 的 MCP 客户端执行。
---

# mcd-host：麦门东道主 · 请客参谋

mcd-host 把麦当劳中国 MCP 的只读能力（门店、菜单、券、营养）变成一个确定性的「凑桌引擎」：你通过 `mcd-host … --json` 操作它，读 JSON 结果，再用自然语言告诉用户。

## 前提

- **需要能在用户本机执行命令。** 只能对话、不能跑命令的环境用不了这个 Skill。
- **安装**（没装时）：
  ```bash
  uv tool install git+https://github.com/jimpablo/mcd-host
  # 没有 uv：
  pip install "git+https://github.com/jimpablo/mcd-host"
  ```
  装好后运行 `mcd-host demo` 确认（合成数据，不需要 Token）。
- **Token 由用户自己配置**：环境变量 `MCD_MCP_TOKEN`、当前目录 `.env`（`MCD_MCP_TOKEN=...`）、或 `~/.config/mcd-mcp/token`（macOS/Linux，`chmod 600`）。不要让用户把 Token 发进对话，不要读取、打印或改写 Token 文件。命令报「没有找到麦当劳 MCP Token」时，告诉用户去 open.mcd.cn/mcp 控制台申请并自己写进上面的位置。没有 Token 时用 `--demo` 演示，并明确告诉用户这是演示数据。

## 必须遵守的规则

1. **一律带 `--json`。** 输出稳定好解析，也不会弹交互提示。不要替用户回答交互问题（mcd-host 本身没有交互写操作，但 `fetch` 之外的命令都只读）。
2. **不直接调用 MCP 写操作 tool**（`create-order`、`cancel-order`、`auto-bind-coupons`、`mall-create-order`、`draw-lottery`、`party-order-create`、`delivery-create-address`），即使你的环境里配了麦当劳 MCP 连接器。下单必须：先把 `mcd-host plan` 的方案（菜品、份数、券、应付、人均）如实告诉用户 → 用户明确说「确认/可以/下单」→ 才由用户自己在 MCP 客户端完成，或经用户同意后由你调用写操作 tool。用户没表态、或改了任何条件（人数、预算、忌口），都要重新生成方案。
3. **mcd-host 只读。** 查门店/菜单/券/营养都是只读工具；不要试图用 mcd-host 改任何账户状态。
4. **金额单位是「分」。** JSON 里的 `price`/`total`/`subtotal`/`payable`/`perPerson`/`threshold`/`value` 都是整数分，告诉用户时除以 100，写成 ¥278.00。`--budget` 是元。
5. **方案要解释。** 把 `rationale`（为什么这么搭、避开了什么忌口、券怎么挑的）和 `warnings`（超预算、热量超标、无合适套餐）一并转告，不要让用户只看到一堆数字。
6. **卡片只本机生成。** `mcd-host card` 只在用户指定路径写 SVG；不要替用户上传或分享，也不要用 GitHub Actions 定时生成（MCP 服务规则不允许把凭证托管到第三方平台）。
7. **出错不盲目重试。** `fetch` 报 401/429 时按提示处理；解析不到菜单时检查是不是 `query-meals` 的返回结构，或让用户先 `mcd-host fetch menu --store-code <code> --out menu.json` 再 `--menu menu.json`。

## 常用流程

| 步骤 | 命令 | 看 JSON 的哪里 |
|---|---|---|
| 查门店 | `mcd-host fetch stores --city 上海 --keyword 人民广场 --json` | `data` 里选一家，记下 `storeCode` |
| 拉菜单 | `mcd-host fetch menu --store-code <code> --json` | `data`：直接作为 plan 的 `menu` |
| 拉券 | `mcd-host fetch coupons --store-code <code> --json` | `data`：`storeCoupons`/`myCoupons`/`availableCoupons` |
| 拉营养 | `mcd-host fetch nutrition --json` | `data`：`foods[]` |
| 凑一桌 | `mcd-host plan --input request.json --json` | `data.lines[]`（`code`/`name`/`kind`/`qty`/`price`/`total`）、`subtotal`、`coupon`、`payable`、`perPerson`、`caloriesPerPerson`、`warnings`、`rationale` |
| 出卡片 | `mcd-host card --plan plan.json -o <路径> --json` | `data.path`（写好的 SVG 绝对路径） |
| 演示 | `mcd-host demo --people 6 --budget 300 --json` | 同上，合成数据 |

`--input request.json` 的格式（Agent 推荐用法，把 MCP 拉到的数据一次给全）：

```json
{
  "request": {
    "people": 6,
    "budget": 300,
    "occasion": "dinner",
    "avoid": ["辣"],
    "prefer": [],
    "must_include": [],
    "max_calories": 900,
    "with_dessert": null
  },
  "menu": { "...query-meals 的返回..." },
  "coupons": { "...query-store-coupons / query-my-coupons 的返回..." },
  "nutrition": { "...list-nutrition-foods 的返回..." }
}
```

- `occasion`：`lunch`/`dinner`/`tea`/`breakfast`/`birthday`/`team`；默认只有晚饭/下午茶/庆生/团餐配甜品。
- `avoid` 是忌口关键词（如「辣」「酸黄瓜」），`prefer` 是偏好，`must_include` 是必点餐品 code。
- 也可以不组装 `--input`，直接 `mcd-host plan --people 6 --budget 300 --menu menu.json --coupons coupons.json --json`（文件用 `fetch … --out` 落盘）。

## 一个完整例子

```text
用户：周六请 6 个同事吃饭，预算 300，有人不吃辣。

你：（fetch stores → fetch menu/coupons/nutrition）
    （写 request.json，然后 mcd-host plan --input request.json --json）
    → lines: 麦辣鸡腿堡套餐×2（避开辣后应为板烧/巨无霸套餐）、玉米杯×3、甜筒×2……
      payable: 27800，coupon: 满100减20，perPerson: 4634
你对用户：6 人晚饭，三种套餐轮换（板烧×2、巨无霸×2、麦香鱼套餐×2），
          已避开所有辣味餐品；小食甜品全桌分享。
          用「满100减20」省 ¥20，应付 ¥278，人均 ¥46.34，人均约 951 千卡。
          要生成方案卡发群里吗？确认后你可以自己在麦当劳 App 下单。

用户：确认，生成卡片。

你：mcd-host card --plan plan.json -o ~/Desktop/host.svg --json
    → data.path: /Users/.../host.svg
你对用户：卡片写好了：<路径>。可以直接发群；下单你自己来，需要我念一遍菜单清单吗？
```

（例中数据为演示值，实际以 MCP 实时返回为准。）
