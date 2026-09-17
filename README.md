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
- **连接自检**：五步定位"配置/网络/账套/登录/权限"到底卡在哪
- **账套自动发现**：不用问实施商要账套 ID，只填账套名称即可
- **字段核对**：查出某个单据在当前账套的权威字段清单，避免猜字段
- 追加官方字段说明中的字段
- 导出全组织数据后再按条件筛选

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

推荐写**用户级配置文件**（技能升级/重装不会覆盖，也不会被误打包分发）：

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
- 兼容旧写法：复制 `config.example.py` 为 `config.py` 并填写。
- 需要多个账套时用 `profiles` 结构 + `KINGDEE_PROFILE` 切换，详见 `SKILL.md`。

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

`官方字段说明/` 保存了各类单据和报表的字段参考。需要临时增加默认未导出的字段时，使用 `--fields`：

```bash
python data_exporter.py --only AR_receivable --fields "AR_receivable:FNOINVOICEAMOUNT"
```

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

`收票单`、`银行存款流水账` 等项目的可选字段，均可在 `官方字段说明/` 中查看。

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
├── data_exporter.py
├── config.example.py
├── requirements.txt
├── scripts/
└── 官方字段说明/
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

会逐步判定 配置 → 服务器连通 → 账套定位 → 登录 → 取数冒烟，哪一步失败就给哪一步的修复动作。
最常见的两种：**WebAPI 白名单没配**（报 `MsgCode 11`，与账号密码无关）和 **密码大小写错**。
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
data_exporter.py         主程序
config.example.py        安全配置示例
requirements.txt         Python 依赖
scripts/                 Excel 二次处理脚本
官方字段说明/            金蝶字段参考
references/              排障手册与查询实战
  error-playbook.md      错误判读与自愈（含白名单配置路径）
  query-cookbook.md      载荷格式、去重口径、状态码、场景配方
agents/openai.yaml       AI 客户端展示信息
```

> 本工具仅用于你有权访问的金蝶环境。使用者需要自行负责凭据保管、权限控制和数据合规。
