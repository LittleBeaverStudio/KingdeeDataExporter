> **本项目采用「小河狸工作室非转售许可 1.0」**——
> 个人使用与**企业内部使用免费**（含内部办公、财务与会计处理、内部系统集成）；
> 对外销售、集成进收费产品或服务、托管 / SaaS / 代运营、以及**向第三方交付成果或提供服务，须事先取得书面授权**。
> 许可全文见 [LICENSE](./LICENSE)。商业授权：https://littlebeaver.top

[![License](https://img.shields.io/badge/License-%E5%B0%8F%E6%B2%B3%E7%8B%B8%E9%9D%9E%E8%BD%AC%E5%94%AE%E8%AE%B8%E5%8F%AF-blue.svg)](./LICENSE)

# 金蝶云星空数据导出 Skill

把金蝶云星空中的单据和报表批量导出为一个多工作表 Excel 文件。适合需要定期取数、经营分析、财务核对或给其他 AI Skill 提供数据的中文用户。

## ✨ 能做什么

- 按日期和组织导出数据
- 一次导出多个单据或报表
- 使用中文名称或 `form_id` 精确选择内容
- 查询全部组织编码
- **连接自检**：六步定位"依赖/配置/网络/账套/登录/权限"到底卡在哪
- **账套自动发现**：不用问实施商要账套 ID，只填账套名称即可
- **对象探查**：列子系统 → 列业务对象（含 FormId）→ 体检能否取数，清单外的对象也能定位
- **字段核对**：查出某个单据在当前账套的权威字段清单，避免猜字段
- 追加官方字段说明中的字段（支持直接写中文名）
- 导出全组织数据后再按条件筛选
- **交付友好的 Excel**：表头加粗、首行冻结、列宽自适应、自动筛选
- **审计日志**：每次取数留一行元数据记录（时间/对象/行数），不记业务内容

> **依赖只有两个**：`pandas` + `openpyxl`。网络、加密、日期全部走 Python 标准库，
> 不需要 `requests` / `python-dateutil` —— 受控内网装不上轮子时这一条很关键。

目前覆盖销售、采购、库存、应收应付、收付款、费用、资金、总账和三大财务报表等常用数据。实际清单以这条命令为准：

```bash
python data_exporter.py --show-config
```

## 🚀 三步开始

### 1. 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 2. 填写配置

**推荐：配置向导（弹窗，明文不落盘）**

```bash
python setup_credentials.py
```

弹窗里**只需填 3 项：公司名（账套名称）、用户名、密码**。凭据用 **Windows 系统加密（DPAPI）**
保存到 `~/.workbuddy/kingdee/credentials.bin` —— 绑当前 Windows 用户，同机其它用户读不出、
拷到别的机器解不开、不在任何 git 仓库内。不写明文、不进对话记录、不落日志。

只看状态不开窗：`python setup_credentials.py --check`

**从旧版明文迁移**：若本机已有 `~/.workbuddy/kingdee/config.json`（密码明文），跑一次向导即可 ——
读入旧值 → 加密保存 → **默认勾选删除该明文文件** → 提示**到金蝶后台修改一次密码**。

**备选：写用户级配置文件**（旧版写法，兼容保留，**不推荐**）

`~/.workbuddy/kingdee/config.json`（Windows：`C:\Users\<你>\.workbuddy\kingdee\config.json`）

```json
{
  "base_url": "https://你的域名/k3cloud/",
  "acct_name": "账套名称",
  "username": "取数账号",
  "password": "密码"
}
```

- **账套 ID 不用自己找** —— 只填 `acct_name`（账套名称）会自动解析；想直接填 `acctid` 就先跑 `--list-datacenters`。
- 也可以用环境变量 `KINGDEE_BASE_URL` / `KINGDEE_ACCTID` / `KINGDEE_ACCT_NAME` / `KINGDEE_USERNAME` / `KINGDEE_PASSWORD`。
  ⚠️ 环境变量**不会被误提交进 git**，但**本地并不保密**（同用户其它进程可读、会进日志与崩溃转储）；
  本机保密请用上面的向导。
- 兼容旧写法：复制 `config.example.py` 为 `config.py` 并填写。
- 需要多个账套时用 `profiles` 结构 + `KINGDEE_PROFILE` 切换，详见 `SKILL.md`。

**读取优先级：环境变量 > 系统加密凭据 > 明文 `config.json` > 技能目录 `config.py`。**

> 🔐 无论哪种方式，都不要把真实账号、密码或账套 ID 提交到公开仓库。

### 3. 自检，然后运行导出

```bash
python data_exporter.py --doctor      # 先确认接通（配置→连通→账套→登录→取数冒烟）
python data_exporter.py               # 再导出
```

不知道从哪开始配，或忘记配置方式时：

```bash
python data_exporter.py --help-config
```

完成后会在当前目录生成类似下面的文件：

```text
云星空经营数据_2026年07月_20260715_120000.xlsx
```

经营数据可能包含敏感信息。建议保存到访问权限受控的目录：

```bash
python data_exporter.py --output-dir "D:/secure/kingdee-exports"
```

## 🧭 推荐使用顺序

第一次使用时，按下面顺序最省事。

### 查看可导出的内容

```bash
python data_exporter.py --show-config
```

### 获取组织编码

```bash
python data_exporter.py --list-orgs
```

生成的组织列表中：

- `number`：组织编码，用于 `--org`
- `name`：组织名称

### 按期间和组织导出

```bash
python data_exporter.py --start 2026-06-01 --end 2026-06-30 --org ORG001
```

### 只导出一种单据或报表

使用中文名称：

```bash
python data_exporter.py --start 2026-06-01 --end 2026-06-30 --org ORG001 --only 销售出库单
```

使用 `form_id`：

```bash
python data_exporter.py --start 2026-06-01 --end 2026-06-30 --org ORG001 --only SAL_OUTSTOCK
```

多个组织或多个项目使用英文逗号分隔：

```bash
python data_exporter.py --org ORG001,ORG002 --only SAL_OUTSTOCK,AR_receivable
```

### 全组织导出

```bash
python data_exporter.py --org all --only 应收单
```

> ⚠️ 全组织数据可能很多，建议同时使用 `--only` 缩小范围。

## 🧩 追加默认字段

`field-docs/` 保存了各类单据和报表的字段参考（每个对象一个文件，按 FormId 命名，如 `AR_receivable.txt`）。需要临时增加默认未导出的字段时，使用 `--fields`：

```bash
python data_exporter.py --only AR_receivable --fields "AR_receivable:FNOINVOICEAMOUNT"
```

也支持直接写中文名（对照表里有的字段）：

```bash
python data_exporter.py --only 应收单 --fields "应收单:价税合计"
```

> 目录用 ASCII 文件名（FormId）而不是中文名，是为了压缩包跨系统解压时不出现乱码。
> 2.3.x 及更早的 `官方字段说明/<中文名>.txt` 布局仍然兼容，代码会自动回退。

Windows 控制台遇到中文参数编码问题时，优先使用字段 key。

### 常用特殊配置

限制银行存款流水账的银行账号时，在本地 `config.py` 中填写：

```python
KINGDEE_CONFIG["bank_account_numbers"] = ["银行账号1", "银行账号2"]
```

财务报表默认按导出期间生成月报，并拆分为资产负债表、利润表和现金流量表。需要季报、半年报或年报时，在 `KINGDEE_CONFIG["financial_report"]` 中调整 `CycleType`：

- `4`：月报
- `5`：季报
- `6`：半年报
- `7`：年报

合并报表还需要根据本企业的云星空报表模板，补充报表编号、会计体系、会计政策和合并范围等参数。

`收票单`、`银行存款流水账` 等项目的可选字段，均可在 `field-docs/` 中查看。

## 🧭 清单外的对象怎么导（对象探查）

凭证、资产卡片、即时库存、二开单据这些不在内置清单里的对象，用 `--form-id` 取数即可，
前提是知道 FormId。不知道就走这条链：

```bash
python data_exporter.py --list-subsystems                      # ① 有哪些模块（GL / AR / STK …）
python data_exporter.py --list-objects --object-sub GL          # ② 该模块下有哪些对象
python data_exporter.py --list-objects --object-kw 凭证         # ③ 只知道名字就跨模块搜
python data_exporter.py --test-form GL_Voucher                 # ④ 体检：元数据 + 取数两关
python data_exporter.py --form-id GL_Voucher --filter-string "FDate>='2026-09-01'"   # ⑤ 取数
```

两个容易踩的点：

- **别按 FormId 前缀猜模块**。动态建模生成的对象 FormId 是数字码或 GUID，不带 `GL` / `AR` 前缀，
  按前缀筛会漏一大片。子系统归属存在 `FSubSystemId` 里，用 `--object-sub` 才筛得全。
- **在册 ≠ 能取数**。注册表里混着单据转换规则、打印模板等非表单对象，`--form-id` 一定失败。
  所以第 ④ 步不能省，`--test-form` 会分开告你卡在「元数据」还是「取数」。

清单可落盘成 JSON，便于脚本化：

```bash
python data_exporter.py --list-objects --object-sub AR --json-out ar_objects.json
```

## 📝 审计日志

每次导出、导出失败、登录失败都会在 `~/.workbuddy/kingdee/audit.log` 追加一行 JSON：

```json
{"ts": "2026-10-17 19:02:47", "action": "export_form", "version": "2.4.1",
 "form": "BD_MATERIAL", "rows": 2908, "output": "BD_MATERIAL_BD_MATERIAL_20261017_190246.xlsx"}
```

只记元数据（时间 / 动作 / 对象 / 组织 / 行数 / 成功与否），**不记业务数据内容、不记账号密码**。
目的是事后能回答「这批数据是什么时候、导了哪个对象、多少行、成功与否」。
**不记录账号名** —— 按本技能的原则「真实账号不进任何日志」，要追到人请结合操作系统的登录审计。
不需要就设 `KINGDEE_AUDIT=0` 关掉。

## 🔎 筛选已导出的 Excel

按组织和单据类型筛选：

```bash
python scripts/filter_export_excel.py --input "导出文件.xlsx" --org ORG001 --bill-type "应收单"
```

只处理一个工作表：

```bash
python scripts/filter_export_excel.py --input "导出文件.xlsx" --sheet "应付单" --org ORG001
```

默认会在原文件旁生成带 `_filtered` 后缀的新文件。

## 🤖 让 AI 工具识别这个 Skill

仓库采用“一个仓库一个 Skill”的通用结构，`SKILL.md` 位于仓库根目录：

```text
KingdeeDataExporter/
├── SKILL.md
├── README.md
├── CHANGELOG.md
├── data_exporter.py
├── setup_credentials.py
├── credstore.py
├── config.example.py
├── requirements.txt
├── scripts/
├── references/
└── field-docs/          # 字段参考，按 FormId 命名（ASCII 文件名）
```

支持从 GitHub 扫描 Skill 的工具，可以直接使用仓库地址：

```text
https://github.com/LittleBeaverStudio/KingdeeDataExporter
```

识别后可这样发起任务：

```text
请使用 kingdee-data-exporter，先帮我查询组织编码，再导出上个月的销售出库单。
```

### SkillHub / 其他管理器

能递归扫描 `SKILL.md` 的 SkillHub 或桌面管理器可以直接识别本仓库。若平台要求上传压缩包，请压缩整个仓库，并确认解压后根目录中仍有 `SKILL.md`。

## 🛠️ 常见问题

### 连接报错，不知道卡在哪

```bash
python data_exporter.py --doctor
```

会逐步判定 运行环境 → 配置 → 服务器连通 → 账套定位 → 登录 → 取数冒烟，哪一步失败就给哪一步的修复动作。
最常见的两种：**WebAPI 白名单没配**（报 `MsgCode 11`，与账号密码无关）和 **密码大小写错**。
（`openpyxl` 缺失会在第 0 步就报出来 —— 否则要等到最后写 Excel 才炸，最难排查。）
完整判读表见 `references/error-playbook.md`。

> ⚠️ 密码连续错约 5 次会锁账号。本工具判读为凭据问题时不自动重试，连续 2 次即中止。

### 不知道账套 ID（acctid）

```bash
python data_exporter.py --list-datacenters
```

这个接口**免账号密码**，第 1 列就是 acctid。或者干脆只填 `acct_name`，由脚本自动解析。

### 不知道组织编码

```bash
python data_exporter.py --list-orgs
```

注意区分：**账套**（acctid，一台服务器上的一个数据中心）≠ **组织**（账套内的核算组织，`--org` 用的编码）。

### 不知道 `--only` 填什么

```bash
python data_exporter.py --show-config
```

### 字段导不出来 / 报"字段不存在"

```bash
python data_exporter.py --inspect-fields ER_ExpReimbursement --filter 发票
```

这是当前账套的**权威**字段清单，查不到就说明该字段确实不存在，不要继续猜。

### 检查是否有新版本

```bash
python data_exporter.py --check-update
```

版本检查默认关闭，只有 `--check-update` 会访问 GitHub Releases API，日常导出不产生额外网络请求。

## 📁 主要文件

```text
SKILL.md                 AI 执行说明与触发描述
README.md                中文使用介绍
CHANGELOG.md             版本变更记录
data_exporter.py         主程序
setup_credentials.py     凭据向导（DPAPI 加密）
credstore.py             凭据存取
config.example.py        安全配置示例
requirements.txt         Python 依赖（仅 pandas + openpyxl）
scripts/                 Excel 二次处理脚本
field-docs/              金蝶字段参考（按 FormId 命名）
references/              排障手册与查询实战
  error-playbook.md      错误判读与自愈（含白名单配置路径）
  query-cookbook.md      载荷格式、去重口径、状态码、场景配方
agents/openai.yaml       AI 客户端展示信息
```

> 本工具仅用于你有权访问的金蝶环境。使用者需要自行负责凭据保管、权限控制和数据合规。
