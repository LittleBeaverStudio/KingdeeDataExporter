# kingdee-data-exporter

一个**自包含**的金蝶 K3Cloud 经营数据导出工具（单据 + 报表），导出为多 Sheet Excel，并可选推送企业微信群机器人。

你只需要发布/下载本目录即可使用。

## 快速开始

### 1) 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 2) 配置金蝶账号（必填）

编辑同目录的 `config.py`，填写 `KINGDEE_CONFIG`：

- `base_url`: 例如 `https://xxxx.ik3cloud.com`
- `acctid`: 账套 ID
- `username` / `password`

企业微信推送（可选）：

- `WECHAT_CONFIG.webhook` 可留空
- 或运行时加 `--no-wechat` 跳过推送

> 安全提示：不要把真实账号密码提交到公开仓库。推荐用 `config.example.py` 复制生成本地 `config.py` 后填写。

### 3) 一键导出（默认导出全部配置项）

```bash
python data_exporter.py
```

会生成类似 `金蝶经营数据_2026年04月_YYYYmmdd_HHMMSS.xlsx` 的文件。

说明：

- 不传 `--org` 时，脚本会登录金蝶后自动读取系统组织并导出，不再写死某家公司的组织编码
- 如果只想导出指定组织，请显式传 `--org`

## 常用命令

### 查看当前可导出的单据/报表清单

```bash
python data_exporter.py --show-config --no-wechat
```

后续 `--only` 参数就填输出里的 `form_id` 或中文名称（支持逗号分隔）。

## 支持的单据与报表

### 单据

- 1. `销售出库单`（`SAL_OUTSTOCK`）
  字段：单据编号、日期、客户、单据类型、销售部门、销售员、备注、物料名称、仓库、税额、金额、价税合计、总成本
- 2. `销售订单`（`SAL_SaleOrder`）
  字段：日期、单据类型、单据编号、单据状态、客户、销售部门、销售员、创建人、关闭状态、物料编码、物料名称、销售单位、销售数量、单价、税额、价税合计、要货日期
- 3. `销售退货单`（`SAL_RETURNSTOCK`）
  字段：单据编号、日期、退货客户、单据类型、销售部门、销售员、备注、物料名称、仓库、税额、金额、价税合计、总成本
- 4. `手工标准应收单`（`AR_receivable`）
  字段：单据类型、单据编号、业务日期、客户、销售组织、销售部门、物料名称、税额、不含税金额、价税合计、创建人、备注
- 5. `应付单`（`AP_Payable`）
  字段：单据类型、业务日期、供应商、单据编号、结算组织、采购部门、物料名称、费用项目名称、费用承担部门、创建人、税额、不含税金额本位币、价税合计本位币、备注
- 6. `采购订单`（`PUR_PurchaseOrder`）
  字段：单据编号、采购日期、供应商、单据状态、采购组织、采购员、创建人、关闭状态、摘要、物料编码、物料名称、采购单位、采购数量、交货日期、单价、税额、价税合计、是否赠品
- 7. `费用申请单`（`ER_ExpenseRequest`）
  字段：单据编号、申请日期、申请人、申请部门、申请组织、费用项目、事由、申请借款、单据状态、关闭状态、申请金额、核定金额
- 8. `费用报销单`（`ER_ExpReimbursement`）
  字段：单据类型、实报实付、单据编号、事由、申请日期、申请人、申请部门、申请组织、退款/付款、费用项目、单据状态、申请报销金额、申请退/付款金额、已付款金额、已退款金额、冲借款金额、冲销金额、报销未付款金额；默认单据状态为全部，作废状态为否
- 9. `出差申请单`（`ER_ExpenseRequest_Travel`）
  字段：单据编号、申请日期、事由、费用项目、申请人、申请部门、申请组织、申请借款、申请金额、单据状态、核定金额、关闭状态；默认单据状态为全部，作废状态为否
- 10. `差旅费报销单`（`ER_ExpReimbursement_Travel`）
  字段：单据类型、实报实付、单据编号、事由、申请日期、申请人、申请部门、申请组织、退款/付款、费用项目、单据状态、申请报销金额、费用承担组织、申请退/付款金额、已付款金额、报销未付款金额、备注；默认单据状态为全部，作废状态为否
- 11. `付款申请单`（`CN_PAYAPPLY`）
  字段：单据类型、单据编号、申请日期、往来单位、币别、应付金额、申请付款金额、结算币别、结算组织、创建人、部门、单据状态、关闭状态、付款用途、到期日、费用项目、备注；默认单据状态为全部，作废状态为否
- 12. `付款单`（`AP_PAYBILL`）
  字段：单据类型、单据编号、业务日期、往来单位类型、往来单位、备注、结算方式、付款用途、付款组织、费用项目、费用承担部门、手续费、表体-实付金额
- 13. `收款单`（`AR_RECEIVEBILL`）
  字段：单据类型、单据编号、业务日期、往来单位类型、结算方式、收款用途、收款组织、销售部门、往来单位、备注、手续费、表体-实收金额
- 14. `付款退款单`（`AP_REFUNDBILL`）
  字段：单据类型、单据编号、业务日期、往来单位、付款单位、结算方式、原付款用途、表体-实退金额、付款组织、部门、费用承担部门、费用项目、备注
- 15. `收款退款单`（`AR_REFUNDBILL`）
  字段：单据类型、单据编号、业务日期、往来单位、结算方式、原收款用途、表体-实退金额、付款组织、销售部门、备注
- 16. `其他应付单`（`AP_OtherPayable`）
  字段：单据类型、单据编号、业务日期、往来单位类型、往来单位、总金额、费用项目名称、申请部门、结算组织、创建人
- 17. `其他应收单`（`AR_OtherRecAble`）
  字段：单据类型、单据编号、业务日期、往来单位类型、往来单位、总金额、费用项目名称、申请部门、结算组织、创建人
- 18. `应付调汇单`（`AP_AdjustExchangeRate`）
  字段：单据编号、往来单位类型、往来单位、业务部门、业务日期、调汇金额

### 报表

- 1. `应付款汇总表`（`AP_SumReport`）
  字段：往来单位编码、往来单位名称、结算组织、(本位币)期初余额、(本位币)本期应付、(本位币)本期付款、(本位币)本期冲销额、(本位币)期末余额
- 2. `应收款汇总表`（`AR_SumReport`）
  字段：往来单位编码、往来单位名称、结算组织、(原币)期初余额、(原币)本期应收、(原币)本期收款、(原币)本期冲销额、(原币)期末余额
- 3. `存货收发存汇总表`（`HS_INOUTSTOCKSUMMARYRPT`）
  字段：物料编码、物料名称、物料分组、仓库、期初数量、期初单价、期初金额、收入数量、收入单价、收入金额、发出数量、发出单价、发出金额、期末数量、期末单价、期末金额
- 4. `存货收发存明细表`（`HS_NoDimInOutStockDetailRpt`）
  字段：期间、单据日期、单据编号、业务类型、单据类型、物料编码、物料名称、收入数量、收入单价、收入金额、发出数量、发出单价、发出金额、期末数量、期末单价、期末金额
- 5. `资金头寸表`（`CN_FundPositionReport`）
  字段：资金类别、银行、账户名称、银行账号、收付组织、内部账户名称、内部账户、原币币别、原币期初余额、原币本日收入、原币本日支出、原币本日余额、本位币币别、本位币期初余额、本位币本日收入、本位币本日支出、本位币本日余额、收入笔数、支出笔数
- 6. `销售出库开票跟踪表`（`SAL_OutStockInvoiceRpt`）
  字段：销售组织、单据编号、单据类型、日期、销售员、客户名称、物料名称、数量、单价、金额、是否赠品、应收数量、应收金额、调整金额、开票数量、开票金额、结算金额、结算调整金额、特殊冲销金额；默认单据状态为已审核，统计套件为全部
- 7. `采购订单执行明细表`（`PUR_PurchaseOrderDetailRpt`）
  字段：采购组织、订单编号、日期、供应商名称、物料名称、交货日期、结算币别、订货数量、价税合计、收料数量、收料金额、入库数量、入库金额、退料数量、退料金额、应付数量、应付金额、先开票数量、先开票金额、开票数量、开票金额、预付金额、已结算金额、结算调整金额、付款核销金额、特殊冲销金额；默认业务类型为全部，单据状态为已审核，行状态为全部

### 先导出全部组织列表（降低配置难度）

```bash
python data_exporter.py --list-orgs --no-wechat
```

会生成 `组织列表_YYYYmmdd_HHMMSS.xlsx`，常用字段：

- `number`: 组织编码（用于 `--org`）
- `name`: 组织名称

### 某期间 + 某组织：导出全部单据/报表

```bash
python data_exporter.py --start 2026-02-01 --end 2026-02-28 --org 101 --no-wechat
```

多个组织（逗号分隔）：

```bash
python data_exporter.py --start 2026-02-01 --end 2026-02-28 --org 101,102,104 --no-wechat
```

如果不确定组织编码，建议先运行 `--list-orgs`。

### 某期间 + 某组织 + 某单据类型明细（只导出 1 个表单/报表）

例如只导出“销售出库单”（`SAL_OUTSTOCK`）：

```bash
python data_exporter.py --start 2026-02-01 --end 2026-02-28 --org 101 --only SAL_OUTSTOCK --no-wechat
```

也可以用中文名（以 `--show-config` 输出为准）：

```bash
python data_exporter.py --start 2026-02-01 --end 2026-02-28 --org 101 --only 销售出库单 --no-wechat
```

### 全组织导出（先“全量”再二次筛选）

```bash
python data_exporter.py --start 2026-02-01 --end 2026-02-28 --org all --no-wechat
```

> 注意：全组织数据量可能很大，建议配合 `--only` 缩小范围。

## 二次筛选（按组织/单据类型从导出 Excel 再筛一遍）

```bash
python scripts/filter_export_excel.py --input "金蝶经营数据_2026年02月_20260401_120000.xlsx" --org 101 --bill-type "手工标准应收单"
```

只处理某一个 Sheet：

```bash
python scripts/filter_export_excel.py --input "金蝶经营数据_2026年02月_20260401_120000.xlsx" --sheet "应付单" --org 101
```

## 通过 OpenClaw 调用（建议）

GitHub 仓库地址：

```text
https://github.com/LittleBeaverStudio/KingdeeDataExporter
```

OpenClaw 的 skill 一般以包含 `SKILL.md` 的目录为单位安装。推荐在 OpenClaw 对话中粘贴上面的仓库地址，并明确说明：

```text
请安装并使用这个 GitHub 仓库里的 KingdeeDataExporter skill，按 SKILL.md 的说明指导我配置 config.py，然后运行金蝶数据导出。
```

如果你的 OpenClaw 环境支持 CLI，也可以尝试用 GitHub 地址安装：

```bash
openclaw skills install github:LittleBeaverStudio/KingdeeDataExporter
```

如果 CLI 不能直接识别该仓库，可以手动安装：下载仓库 ZIP，解压后确认目录中包含 `SKILL.md`、`data_exporter.py`、`requirements.txt`，再把整个目录复制到 OpenClaw 的 skills 目录（常见位置为 `~/.openclaw/skills/KingdeeDataExporter`）。之后在 OpenClaw 对话里说“使用 kingdee-data-exporter skill 导出金蝶数据”，OpenClaw 会根据 `SKILL.md` 引导安装依赖、填写 `config.py` 并执行导出命令。

> 注意：不要把真实的金蝶账号、密码、数据中心 ID 写进公开对话或提交到 GitHub。只在本地 `config.py` 中填写真实配置。

## 通过 WorkBuddy 调用

WorkBuddy 可以导入压缩文件后使用。建议先把本仓库打包成 ZIP，或直接从 GitHub 下载 ZIP，导入 WorkBuddy 的 skill/技能管理入口。

导入后确认压缩包根目录包含这些文件：

- `SKILL.md`
- `data_exporter.py`
- `requirements.txt`
- `config.example.py`
- `scripts/filter_export_excel.py`

在 WorkBuddy 中可以这样发起任务：

```text
请使用 kingdee-data-exporter skill，帮我配置并运行金蝶 K3Cloud 经营数据导出。
```

首次使用时按 WorkBuddy 的提示完成以下步骤：

1. 安装依赖：`python -m pip install -r requirements.txt`
2. 复制 `config.example.py` 为 `config.py`
3. 在 `config.py` 中填写 `KINGDEE_CONFIG`，包括 `base_url`、`acctid`、`username`、`password`
4. 先运行 `python data_exporter.py --list-orgs --no-wechat` 获取组织编码
5. 再按期间、组织和单据类型运行导出命令，例如：

```bash
python data_exporter.py --start 2026-02-01 --end 2026-02-28 --org 101 --no-wechat
```

如果只想导出某一种单据或报表，先让 WorkBuddy 执行 `python data_exporter.py --show-config` 查看可用清单，再用 `--only` 指定名称或 `form_id`。

