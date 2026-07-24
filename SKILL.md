---
name: kingdee-data-exporter
description: 金蝶云星空经营数据导出技能。仅当用户明确要求从金蝶云星空或 K3 Cloud 查询、导出经营数据时使用；支持配置账号、查询组织和可用单据/报表，按期间、组织及单据或报表类型导出多工作表 Excel，也支持追加官方字段、全组织导出和结果二次筛选。
---

# 金蝶云星空数据导出

使用本技能把金蝶云星空中的单据和报表导出为一个多工作表 Excel 文件。

## 工作原则

1. 先确认用户拥有目标金蝶环境和数据的合法访问权限。
2. 不在对话、日志或公开仓库中展示真实账号、密码、账套 ID 或业务数据。
3. 首次使用时先引导用户从 `config.example.py` 创建本地 `config.py`。
4. 不确定组织编码时，先运行 `--list-orgs`。
5. 不确定单据或报表名称时，先运行 `--show-config`。
6. 数据量可能较大时，优先使用 `--org` 和 `--only` 缩小范围。

## 权限与行为声明

运行本技能前请知悉其能力范围：

- **网络访问**：
  - 连接 `KINGDEE_CONFIG.base_url` 指定的金蝶云星空服务器（登录与取数，必需）；
  - 仅显式传入 `--check-update` 时访问 GitHub Releases API 查询新版本，默认不检查。
- **本地文件读写**：读取 `config.py`（含金蝶凭据，已通过 `.gitignore` 排除，请勿提交公开仓库）和 `官方字段说明/`；默认在当前目录写入导出的 Excel，也可用 `--output-dir` 指定目录。
- **环境变量**：未创建 `config.py` 时，读取 `KINGDEE_BASE_URL`、`KINGDEE_ACCTID`、`KINGDEE_USERNAME`、`KINGDEE_PASSWORD` 作为配置来源。
- 不启动子进程，不访问上述范围之外的网络和文件。

## 首次配置

在技能目录中执行：

```bash
python -m pip install -r requirements.txt
```

复制 `config.example.py` 为 `config.py`，填写：

- `KINGDEE_CONFIG.base_url`：金蝶云星空地址
- `KINGDEE_CONFIG.acctid`：账套 ID
- `KINGDEE_CONFIG.username`：用户名
- `KINGDEE_CONFIG.password`：密码

`config.py` 已被 `.gitignore` 忽略。始终保留这一规则。

## 推荐流程

### 1. 查看支持内容

```bash
python data_exporter.py --show-config
```

输出中的 `form_id` 或中文名称都可以传给 `--only`。

### 2. 获取组织编码

```bash
python data_exporter.py --list-orgs
```

生成的组织列表中，`number` 是后续 `--org` 使用的组织编码。

### 3. 按条件导出

```bash
python data_exporter.py --start 2026-01-01 --end 2026-01-31 --org ORG001
```

只导出一种单据或报表：

```bash
python data_exporter.py --start 2026-01-01 --end 2026-01-31 --org ORG001 --only 销售出库单
```

多个组织或多个项目使用英文逗号分隔：

```bash
python data_exporter.py --org ORG001,ORG002 --only SAL_OUTSTOCK,AR_receivable
```

全组织导出：

```bash
python data_exporter.py --org all --only 应收单
```

将敏感经营数据保存到用户确认的目录：

```bash
python data_exporter.py --org ORG001 --output-dir "D:/secure/kingdee-exports"
```

## 追加官方字段

先在 `官方字段说明/` 中查找字段，再用 `--fields` 追加默认未导出的字段：

```bash
python data_exporter.py --only AR_receivable --fields "AR_receivable:FNOINVOICEAMOUNT"
```

Windows 控制台出现中文参数编码问题时，优先使用字段 key。

## 二次筛选 Excel

对已经导出的 Excel 按组织或单据类型筛选：

```bash
python scripts/filter_export_excel.py --input "导出文件.xlsx" --org ORG001 --bill-type "应收单"
```

只处理某个工作表：

```bash
python scripts/filter_export_excel.py --input "导出文件.xlsx" --sheet "应付单" --org ORG001
```

## 常用补充命令

检查新版本（唯一会访问 GitHub 的选项）：

```bash
python data_exporter.py --check-update
```

日常导出默认不检查更新、不访问 GitHub，无需额外参数。

## 结果检查

导出完成后：

1. 向用户说明生成文件的完整路径。
2. 检查所需工作表是否存在、是否有数据。
3. 若结果为空，依次核对日期、组织权限、单据状态和 `--only` 名称。
4. 不读取或展示超出用户请求范围的敏感业务数据。
