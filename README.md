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

当前已包含的新增单据：

- `销售订单`（`SAL_SaleOrder`）
- `采购订单`（`PUR_PurchaseOrder`）

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

## 发布到 OpenClaw（建议）

- 直接把本目录发布为 GitHub 公共仓库（或仓库子目录）
- 在 OpenClaw 对话中引导用户：
  - 下载/安装该目录
  - 将 `config.example.py` 复制为 `config.py`，再填写 `KINGDEE_CONFIG`
  - 运行示例命令（某期间 + 某组织 + 某单据类型用 `--start --end --org --only`）

