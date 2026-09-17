# -*- coding: utf-8 -*-
# 金蝶云星空经营数据（多表）导出脚本
#
# 说明：
# - 本文件是一个自包含版本，用于随 Skill 目录一起发布
# - 配置位于同目录 `config.py`

import argparse
import requests
import json
import sys
import os
import copy
import re
from datetime import datetime, timedelta
from pathlib import Path
from dateutil.relativedelta import relativedelta

try:
    import pandas as pd
except ModuleNotFoundError:
    print("缺少依赖库 pandas。请执行：python -m pip install -r requirements.txt")
    raise


APP_VERSION = "2026-09-17"
RELEASES_API_URL = "https://api.github.com/repos/LittleBeaverStudio/KingdeeDataExporter/releases/latest"
RELEASES_PAGE_URL = "https://github.com/LittleBeaverStudio/KingdeeDataExporter/releases/latest"

# ────────────────────────── 凭据来源 ──────────────────────────
# 优先级（高 → 低）：
#   1) 环境变量 KINGDEE_BASE_URL / KINGDEE_ACCTID / KINGDEE_ACCT_NAME
#      / KINGDEE_USERNAME / KINGDEE_PASSWORD
#   2) 用户级配置 ~/.workbuddy/kingdee/config.json
#      （推荐：在技能目录之外，升级/重装技能不会覆盖，也不会被误打包分发）
#   3) 技能目录内的 config.py（早期版本写法，继续兼容）
USER_CONFIG_PATH = Path.home() / ".workbuddy" / "kingdee" / "config.json"

# 除连接信息外，用户配置里允许透传的可选键
_OPTIONAL_CONFIG_KEYS = (
    "account_book_number",
    "account_book_numbers",
    "bank_account_numbers",
    "financial_report",
)


def _normalize_base_url(base_url):
    """补全 base_url：确保以 /k3cloud/ 结尾，且不会重复拼接。

    用户经常写漏 `/k3cloud/`，那会导致 403 空响应（很容易被误判成"账号密码错"）。
    """
    text = str(base_url or "").strip().rstrip("/")
    if not text:
        return ""
    if text.lower().endswith("/k3cloud"):
        return text + "/"
    return text + "/k3cloud/"


def _read_user_config_json():
    """读取 ~/.workbuddy/kingdee/config.json。

    支持两种写法：
      A) 扁平：{"base_url": ..., "acct_name": ..., "username": ..., "password": ...}
      B) 多账套：{"default": "a", "profiles": {"a": {...}, "b": {...}}}
    """
    if not USER_CONFIG_PATH.is_file():
        return None
    try:
        data = json.loads(USER_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] 无法解析用户配置 {USER_CONFIG_PATH}：{exc}")
        return None
    if not isinstance(data, dict) or not data:
        return None

    profiles = data.get("profiles")
    if isinstance(profiles, dict) and profiles:
        want = (os.getenv("KINGDEE_PROFILE") or "").strip() or str(data.get("default") or "").strip()
        if not want:
            want = next(iter(profiles))
        picked = profiles.get(want)
        if not isinstance(picked, dict):
            print(f"[WARN] 用户配置里没有 profile「{want}」，可用：{', '.join(profiles)}")
            return None
        common = {k: v for k, v in data.items() if k not in ("profiles", "default")}
        return {**common, **picked, "_profile": want}

    return dict(data)


def load_kingdee_config():
    """按优先级加载金蝶连接配置，返回 dict（含 `_source` 说明来源，不含明文口令的打印）。"""
    env_base = (os.getenv("KINGDEE_BASE_URL") or "").strip()
    if env_base:
        return {
            "base_url": env_base,
            "acctid": (os.getenv("KINGDEE_ACCTID") or "").strip(),
            "acct_name": (os.getenv("KINGDEE_ACCT_NAME") or "").strip(),
            "username": (os.getenv("KINGDEE_USERNAME") or "").strip(),
            "password": os.getenv("KINGDEE_PASSWORD") or "",
            "_source": "环境变量 KINGDEE_*",
        }

    user_cfg = _read_user_config_json()
    if user_cfg and str(user_cfg.get("base_url") or "").strip():
        profile = user_cfg.pop("_profile", "")
        user_cfg["_source"] = str(USER_CONFIG_PATH) + (f"（profile: {profile}）" if profile else "")
        return user_cfg

    try:
        from config import KINGDEE_CONFIG as local_cfg  # 技能目录内配置（早期写法）
        if isinstance(local_cfg, dict) and str(local_cfg.get("base_url") or "").strip():
            cfg = dict(local_cfg)
            cfg["_source"] = "技能目录 config.py"
            return cfg
    except ModuleNotFoundError:
        pass
    except Exception as exc:
        print(f"[WARN] 读取技能目录 config.py 失败：{exc}")

    return {
        "base_url": "",
        "acctid": "",
        "acct_name": "",
        "username": "",
        "password": "",
        "_source": "未配置",
    }


KINGDEE_CONFIG = load_kingdee_config()

# ────────────────────────── 错误判读表 ──────────────────────────
# 同一句"登录失败"背后的原因完全不同：白名单没配 ≠ 密码错 ≠ 账套 ID 错。
# 这里把高频故障拆开，给出「根因 + 下一步动作」，避免用户反复盲试（盲试会锁号）。
ERROR_HINTS = (
    ("未指定允许调用WebAPI接口",
     "该账号没有被加入 WebAPI 白名单（最高频故障，与账号密码无关）。\n"
     "    让金蝶管理员操作：基础管理 → 公共设置 → 参数设置 → 基础管理 → BOS平台 → WebAPI\n"
     "      → 「允许调用WebAPI接口用户」加入取数账号 → 保存（同页「白名单设置」可配可访问 IP）。\n"
     "    注意：不是在「系统管理 → 用户管理」里勾选。"),
    ("数据中心无法获取到",
     "账套 ID（acctid）不对。\n"
     "    执行 `python data_exporter.py --list-datacenters` 按账套名称查出正确的 Id；\n"
     "    或在配置里改填 acct_name（账套名称），脚本会自动解析。"),
    ("CheckPasswordPolicy", "账套已定位成功，是用户名或密码错。注意大小写（Hg ≠ HG）与首尾空格。"),
    ("用户名或密码错误", "账号或密码错，注意大小写与首尾空格。"),
    ("会话信息已丢失", "会话过期。重新执行一次命令即可（脚本每次都会重新登录）。"),
    ("没有权限", "该账号缺少对应模块权限，找管理员开通，或换一个有权限的取数账号。"),
    ("不允许", "账号权限或单据状态限制，先确认该账号在网页端能否打开这个单据。"),
    ("元数据中标识为", "字段标识在当前账套不存在。用 `--inspect-fields <FormId>` 核对字段清单。"),
    ("当前查询串无法解析", "字段名语法错（用了中文名或点号拼写）。改用英文标识（如 FBillNo）。"),
    ("业务对象不存在", "FormId 写错。用 `--show-config` 看内置清单，或用 `--inspect-fields` 验证。"),
    ("接口参数 data 不能为空", "请求载荷格式不对（这是本工具内部错误，请反馈）。"),
)


def error_hint_for(text):
    """按错误原文给出根因与下一步动作；没有命中时返回空串。"""
    body = str(text or "")
    for key, hint in ERROR_HINTS:
        if key in body:
            return hint
    return ""


def print_config_guide(reason=""):
    """配置缺失/不可用时的引导（对用户与 agent 都友好）。"""
    example = {
        "base_url": "https://你的域名/k3cloud/",
        "acct_name": "账套名称（不用填 acctid）",
        "username": "取数账号",
        "password": "密码",
    }
    print("=" * 64)
    print("未检测到可用的金蝶连接配置" + (f"：{reason}" if reason else ""))
    print("=" * 64)
    print("请任选一种方式配置（推荐方式一）：")
    print()
    print(f"方式一（推荐，技能升级/重装不会覆盖）：写 {USER_CONFIG_PATH}")
    print(json.dumps(example, ensure_ascii=False, indent=2))
    print()
    print("方式二（环境变量，不落盘）：")
    print("  KINGDEE_BASE_URL / KINGDEE_ACCTID / KINGDEE_ACCT_NAME")
    print("  / KINGDEE_USERNAME / KINGDEE_PASSWORD")
    print()
    print("方式三（兼容旧写法）：复制 config.example.py 为 config.py 并填写")
    print()
    print("提示：")
    print("  · 账套 ID 不用自己找 —— 填 acct_name 即可，或用下面命令列出全部账套：")
    print("      python data_exporter.py --list-datacenters")
    print("  · 首次配置完请先自检，它会逐步告诉你卡在哪一步：")
    print("      python data_exporter.py --doctor")
    print("=" * 64)


def get_missing_config_keys(cfg):
    """返回缺失的必填项名称列表；acctid 与 acct_name 二者有一即可。"""
    missing = []
    if not str(cfg.get("base_url") or "").strip():
        missing.append("base_url（金蝶地址）")
    if not (str(cfg.get("acctid") or "").strip() or str(cfg.get("acct_name") or "").strip()):
        missing.append("acctid 或 acct_name（账套 ID / 账套名称，二者填一）")
    if not str(cfg.get("username") or "").strip():
        missing.append("username（取数账号）")
    if not str(cfg.get("password") or ""):
        missing.append("password（密码）")
    return missing


# ────────────────────────── 网络与自检工具 ──────────────────────────


def _make_session():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def probe_server(base_url, timeout=10):
    """探测服务器是否可达。返回 (状态码 或 None, 说明)。"""
    url = _normalize_base_url(base_url)
    if not url:
        return None, "未配置 base_url"
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=False)
    except requests.exceptions.SSLError as exc:
        return None, f"SSL 握手失败：{exc}（地址可能是 http/https 写错，或证书不受信）"
    except requests.exceptions.ConnectionError as exc:
        return None, f"连不上服务器：{exc}（检查地址、网络/VPN、防火墙）"
    except Exception as exc:
        return None, f"请求异常：{exc}"
    if resp.status_code == 403 and not (resp.text or "").strip():
        return 403, "返回 403 且内容为空，通常是 URL 路径不对（漏了 /k3cloud/，或地址指向了网关/WAF）"
    return resp.status_code, str(resp.headers.get("Content-Type") or "")


def fetch_datacenters(base_url, timeout=30):
    """拉取数据中心（账套）列表。

    该接口**免认证**，不需要账号密码，所以在配置 acctid 之前就能用。
    返回 [{id, name, number, db}]，其中 id 就是要填的 acctid。
    """
    import base64 as _b64
    import gzip as _gzip

    url = _normalize_base_url(base_url) + (
        "Kingdee.BOS.ServiceFacade.ServicesStub.Account.AccountService."
        "GetDataCenterList.common.kdsvc"
    )
    resp = requests.post(url, json={}, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}：{(resp.text or '')[:200]}")

    raw_text = (resp.text or "").strip()
    data = None
    try:
        data = resp.json()
    except Exception:
        data = None
    if data is None or isinstance(data, str):
        text = data if isinstance(data, str) else raw_text
        text = (text or "").strip()
        if text.startswith("H4sI"):  # 部分环境把响应 base64+gzip 后再返回
            text = _gzip.decompress(_b64.b64decode(text)).decode("utf-8", "replace")
        try:
            data = json.loads(text)
        except Exception as exc:
            raise RuntimeError(f"账套列表不是可解析的 JSON：{raw_text[:200]}") from exc

    rows = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("Data", "data", "DataCenterList", "Result"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break

    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        lower = {str(k).lower(): v for k, v in item.items()}
        acct_id = str(lower.get("id") or "").strip()
        if not acct_id:
            continue
        out.append({
            "id": acct_id,
            "name": str(lower.get("name") or "").strip(),
            "number": str(lower.get("number") or "").strip(),
            "db": str(lower.get("dbid") or lower.get("database") or "").strip(),
        })
    return out


def resolve_acctid_by_name(base_url, acct_name, datacenters=None):
    """用账套名称解析 acctid。返回 (acctid, 说明文本)；解析不出来时 acctid 为空字符串。"""
    name = str(acct_name or "").strip()
    if not name:
        return "", ""
    try:
        centers = datacenters if datacenters is not None else fetch_datacenters(base_url)
    except Exception as exc:
        return "", f"拉取账套列表失败：{exc}"
    hits = [c for c in centers if c["name"] == name] or [c for c in centers if name in c["name"]]
    if len(hits) == 1:
        return hits[0]["id"], f"按账套名称「{name}」解析到 acctid={hits[0]['id']}"
    if len(hits) > 1:
        shown = "、".join(f"{c['name']}({c['id']})" for c in hits)
        return "", f"账套名称「{name}」匹配到多个：{shown}。请写完整名称，或直接填 acctid。"
    available = "、".join(c["name"] for c in centers[:10]) or "（服务器返回的账套列表为空）"
    return "", f"账套名称「{name}」不在该服务器的账套列表里。可用账套：{available}"


def perform_login(session, base_url, acctid, username, password, timeout=30):
    """登录金蝶，返回 (是否成功, 判读信息 dict)。

    把「白名单未配 / 账套 ID 错 / 密码错 / URL 错」拆开判读——它们表现都是"登录失败"，
    但处理方式完全不同，混成一句会让用户反复盲试（盲试会锁号）。
    """
    url = _normalize_base_url(base_url) + (
        "Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc"
    )
    payload = {"acctid": acctid, "username": username, "password": password, "lcid": 2052}
    try:
        resp = session.post(url, json=payload, timeout=timeout)
    except Exception as exc:
        return False, {
            "stage": "网络",
            "message": f"请求失败：{exc}",
            "hint": "确认服务器地址可达、URL 含 /k3cloud/、内网/VPN 已连接。",
        }
    if resp.status_code != 200:
        hint = "HTTP 403 且空响应通常是 URL 路径错（漏了 /k3cloud/）；502/504 多为网关或代理问题。"
        return False, {
            "stage": "网络",
            "message": f"HTTP {resp.status_code}：{(resp.text or '')[:200]}",
            "hint": hint,
        }
    try:
        data = resp.json()
    except Exception:
        return False, {
            "stage": "响应解析",
            "message": f"返回内容不是 JSON：{(resp.text or '')[:200]}",
            "hint": "地址可能指向了非金蝶站点（或在网关/代理页面上）。确认 base_url 是金蝶云星空的 /k3cloud/ 地址。",
        }
    if not isinstance(data, dict):
        return False, {"stage": "响应解析", "message": f"返回结构异常：{str(data)[:200]}", "hint": ""}
    if data.get("LoginResultType") == 1:
        return True, {"stage": "登录", "message": "登录成功", "session_id": data.get("KDSVCSessionId", "")}

    message = str(data.get("Message") or "").strip() or json.dumps(data, ensure_ascii=False)[:200]
    code = data.get("MessageCode", data.get("MsgCode"))
    hint = error_hint_for(message) or error_hint_for(json.dumps(data, ensure_ascii=False))
    return False, {
        "stage": "登录",
        "message": message,
        "code": code,
        "hint": hint or "核对账号、密码（注意大小写与首尾空格）。密码连续错约 5 次会锁号，不要反复重试。",
    }


def query_rows_once(session, base_url, form_id, field_keys, limit=1, filter_string=""):
    """最小化 ExecuteBillQuery（只取少量行），用于自检。

    ⚠️ `data` 必须是 JSON **字符串**；传 dict 会报「接口参数 data 不能为空」。
    """
    url = _normalize_base_url(base_url) + (
        "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
    )
    payload = {
        "formid": form_id,
        "data": json.dumps({
            "FormId": form_id,
            "FieldKeys": field_keys,
            "FilterString": filter_string,
            "OrderString": "",
            "TopRowCount": 0,
            "StartRow": 0,
            "Limit": limit,
        }, ensure_ascii=False),
    }
    resp = session.post(url, json=payload, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}：{(resp.text or '')[:150]}")
    result = resp.json()
    if not isinstance(result, list):
        raise RuntimeError(f"返回结构异常：{json.dumps(result, ensure_ascii=False)[:200]}")
    # 服务端会**把错误包装成数据行**返回（元素是 dict），不抛异常 → 必须先判掉
    for row in result:
        if isinstance(row, dict) or (isinstance(row, list) and any(isinstance(x, dict) for x in row)):
            text = json.dumps(row, ensure_ascii=False)[:300]
            raise RuntimeError(f"接口返回错误对象：{text}\n      {error_hint_for(text)}")
    return result


def fetch_business_info(session, base_url, form_id):
    """查询业务对象元数据（实体 + 字段全清单）。

    ⚠️ 载荷必须是 `{"data": {"FormId": ...}}`（外面要包一层 data）。
    """
    url = _normalize_base_url(base_url) + (
        "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.QueryBusinessInfo.common.kdsvc"
    )
    resp = session.post(url, json={"data": {"FormId": form_id}}, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}：{(resp.text or '')[:200]}")
    data = resp.json()
    result = data.get("Result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise RuntimeError(f"返回结构异常：{json.dumps(data, ensure_ascii=False)[:200]}")
    status = result.get("ResponseStatus") or {}
    if not status.get("IsSuccess"):
        errors = status.get("Errors") or []
        message = "；".join(str(e.get("Message") or e) for e in errors) or json.dumps(status, ensure_ascii=False)[:200]
        raise RuntimeError(f"查询失败：{message}\n      {error_hint_for(message)}")
    return result.get("NeedReturnData") or {}


def _meta_name(name_value):
    """元数据里的 Name 是 [{'Key':2052,'Value':'中文名'}, ...]，优先取简体中文。"""
    if isinstance(name_value, str):
        return name_value
    if isinstance(name_value, list):
        for item in name_value:
            if isinstance(item, dict) and item.get("Key") == 2052:
                return str(item.get("Value") or "")
        for item in name_value:
            if isinstance(item, dict) and item.get("Value"):
                return str(item["Value"])
    return ""


def print_business_info(need_return_data, keyword="", json_out=""):
    """打印业务对象的实体与字段清单；keyword 命中 Key/Name/FieldName 时只显示这些字段。"""
    form_id = need_return_data.get("Id") or ""
    form_name = _meta_name(need_return_data.get("Name"))
    entries = need_return_data.get("Entrys") or []
    total_fields = sum(len(e.get("Fields") or []) for e in entries if isinstance(e, dict))

    kw = str(keyword or "").strip().lower()
    print(f"FormId: {form_id}    {form_name}")
    print(f"实体 {len(entries)} 个 / 字段 {total_fields} 个" + (f"（筛选：{keyword}）" if kw else ""))
    print("-" * 72)

    matched = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fields = entry.get("Fields") or []
        shown = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            key = str(field.get("Key") or "")
            text = f"{key} {field.get('Name') or ''} {field.get('FieldName') or ''}".lower()
            if kw and kw not in text:
                continue
            shown.append(field)
        if kw and not shown:
            continue
        header = f"[{entry.get('Key')}] {_meta_name(entry.get('Name'))}   ({len(fields)} 字段"
        header += f"，命中 {len(shown)})" if kw else ")"
        print(header)
        for field in shown:
            matched += 1
            name = _meta_name(field.get("Name")).strip()
            marks = []
            lookup = str(field.get("LookUpObjectFormId") or "").strip()
            if lookup:
                marks.append(f"引用 {lookup}")
            if str(field.get("MustInput") or "0").strip() not in ("0", "", "False", "false"):
                marks.append("必填")
            suffix = f"   [{'，'.join(marks)}]" if marks else ""
            print(f"    {str(field.get('Key') or ''):<34} {name}{suffix}")
        print()

    if kw and matched == 0:
        print(f"没有字段命中「{keyword}」。")
        print("提示：这是**权威**字段清单——查不到说明该字段在当前账套确实不存在，")
        print("      不要继续猜字段名（猜出来的标识会直接报错）。")
    print("-" * 72)
    print(f"字段总数 {total_fields}（实体：{'、'.join(str(e.get('Key')) for e in entries if isinstance(e, dict))}）")

    if json_out:
        try:
            path = Path(json_out).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(need_return_data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"完整元数据已保存：{path}")
        except Exception as exc:
            print(f"[WARN] 元数据落盘失败：{exc}")


def print_datacenters(base_url):
    """列出服务器上的全部账套（acctid 来源）。"""
    print(f"服务器：{_normalize_base_url(base_url)}")
    try:
        centers = fetch_datacenters(base_url)
    except Exception as exc:
        print(f"拉取账套列表失败：{exc}")
        print("  → 检查 base_url 是否正确、能否在浏览器打开金蝶登录页（URL 需含 /k3cloud/）。")
        return 1
    if not centers:
        print("服务器没有返回任何账套。确认该地址指向的是金蝶云星空站点（而不是网关或其它系统）。")
        return 1
    print(f"共 {len(centers)} 个账套（第 1 列就是要填的 acctid）：")
    print("-" * 72)
    for item in centers:
        suffix = f"    [{item['number']}]" if item["number"] else ""
        print(f"{item['id']}    {item['name']}{suffix}")
    print("-" * 72)
    print("把第 1 列的值填到配置的 acctid；或者只填 acct_name（账套名称），由脚本自动解析。")
    return 0


def _doctor_smoke(session, base_url):
    """取数冒烟：能真的从账套里读出数据，才算接通。返回 (是否通过, 说明)。"""
    attempts = (
        ("ORG_Organizations", "FNumber,FName", "组织基础资料"),
        ("BD_Organization", "FNumber,FName", "组织基础资料"),
        ("BD_MATERIAL", "FNumber,FName", "物料基础资料"),
    )
    last_error = ""
    for form_id, field_keys, label in attempts:
        try:
            rows = query_rows_once(session, base_url, form_id, field_keys, limit=1)
        except Exception as exc:
            last_error = str(exc)
            continue
        if rows:
            return True, f"{label}（{form_id}）可读取"
        last_error = f"{label}（{form_id}）查询成功但返回 0 行"
    return False, (
        f"{last_error}\n"
        "      连接与登录都是通的，但读不到业务数据。按顺序排查：\n"
        "        1) 该账号在网页端能否打开对应单据/基础资料？打不开 → 缺模块权限，找管理员开通。\n"
        "        2) 单据菜单发布到多个应用但许可未买全时，需要在网页端确认许可状态。\n"
        "        3) 换一个在网页端确认有权限的账号再自检。"
    )


def run_doctor():
    """五步自检：配置 → 连通 → 账套 → 登录 → 取数冒烟。逐步给出可执行的下一步。"""
    cfg = KINGDEE_CONFIG
    print("=" * 64)
    print(f"金蝶连接自检（KingdeeDataExporter {APP_VERSION}）")
    print("=" * 64)
    print(f"配置来源：{cfg.get('_source')}")
    print(f"服务器：{_normalize_base_url(cfg.get('base_url')) or '（未配置）'}")
    print(f"账套：{str(cfg.get('acctid') or '').strip() or cfg.get('acct_name') or '（未配置）'}")
    print(f"账号：{str(cfg.get('username') or '').strip() or '（未配置）'}")
    print()

    # 1) 配置完整性
    missing = get_missing_config_keys(cfg)
    if missing:
        print("[1/5] 配置完整性 …… 未通过")
        print(f"      缺少：{'、'.join(missing)}")
        print()
        print_config_guide("配置不完整")
        return 3
    print("[1/5] 配置完整性 …… 通过")

    base_url = _normalize_base_url(cfg.get("base_url"))

    # 2) 服务器连通
    status, detail = probe_server(base_url)
    if status is None:
        print("[2/5] 服务器连通 …… 未通过")
        print(f"      {detail}")
        print("      → 确认浏览器能打开金蝶登录页；URL 必须含 /k3cloud/；内网访问需连 VPN。")
        return 3
    print(f"[2/5] 服务器连通 …… 通过（HTTP {status}）")

    # 3) 账套定位
    acctid = str(cfg.get("acctid") or "").strip()
    centers = None
    try:
        centers = fetch_datacenters(base_url)
    except Exception as exc:
        print(f"[3/5] 账套定位 …… 跳过（无法拉取账套列表：{exc}）")
    if centers:
        if acctid:
            hit = [c for c in centers if c["id"] == acctid]
            if hit:
                print(f"[3/5] 账套定位 …… 通过（{hit[0]['name']}）")
            else:
                print("[3/5] 账套定位 …… 未通过：配置里的 acctid 不在这台服务器的账套列表里")
                print("      可用账套：")
                for item in centers[:15]:
                    print(f"        {item['id']}    {item['name']}")
                print("      → 改用上面的 Id，或把配置里的 acctid 换成 acct_name（账套名称）。")
                return 3
        else:
            resolved, note = resolve_acctid_by_name(base_url, cfg.get("acct_name"), centers)
            if not resolved:
                print(f"[3/5] 账套定位 …… 未通过：{note}")
                return 3
            acctid = resolved
            print(f"[3/5] 账套定位 …… 通过（{note}）")

    # 4) 登录
    session = _make_session()
    ok, info = perform_login(session, base_url, acctid, cfg.get("username"), cfg.get("password"))
    if not ok:
        print("[4/5] 登录 …… 未通过")
        print(f"      错误原文：{info.get('message')}")
        if info.get("code") not in (None, ""):
            print(f"      错误码：{info['code']}")
        if info.get("hint"):
            print(f"      → {info['hint']}")
        return 3
    print("[4/5] 登录 …… 通过")

    # 5) 取数冒烟
    smoke_ok, smoke_detail = _doctor_smoke(session, base_url)
    if not smoke_ok:
        print("[5/5] 取数冒烟 …… 未通过")
        print(f"      {smoke_detail}")
        return 3
    print(f"[5/5] 取数冒烟 …… 通过（{smoke_detail}）")

    print()
    print("=" * 64)
    print("结论：全部通过，可以正常取数。")
    print("下一步：python data_exporter.py --show-config   # 看可导出的单据与报表")
    print("=" * 64)
    return 0


class SalesDataExporter:
    """销售单据数据导出器"""

    def __init__(self, start_date=None, end_date=None, org_numbers=None, only=None, extra_fields=None, output_dir="."):
        self.kingdee_config = dict(KINGDEE_CONFIG)
        self.session = _make_session()
        self.base_url = _normalize_base_url(self.kingdee_config.get("base_url"))
        self.output_dir = Path(output_dir).expanduser().resolve()
        self._login_ok = False
        self._login_fail_count = 0

        # 配置缺失时不在这里中断 —— 否则 `--show-config` 也用不了。
        # 真正需要登录时会明确报错并给出配置引导。
        self._missing_config = get_missing_config_keys(self.kingdee_config)
        if self._missing_config:
            print(f"[提示] 当前还没有可用的金蝶连接配置（缺少：{'、'.join(self._missing_config)}）。")
            print("       查看配置方法：python data_exporter.py --help-config")
            print("       配置完成后自检：python data_exporter.py --doctor")
            print()

        self.only = self._normalize_only(only)
        self.official_fields_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "官方字段说明")
        self.official_field_cache = {}
        self.requested_extra_fields = self._parse_extra_fields(extra_fields)
        self.requested_org_numbers = self._parse_org_numbers(org_numbers) if org_numbers else None

        # 日期范围：默认 1-6 号导出上月整月，7 号及以后导出当月 1 号到今天
        if start_date and end_date:
            self.start_date = start_date
            self.end_date = end_date
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            self.period_name = start_dt.strftime("%Y年%m月")
            self.year = start_dt.year
            self.period = start_dt.month
        else:
            today = datetime.now()
            if today.day <= 6:
                first_day_this_month = today.replace(day=1)
                last_day_last_month = first_day_this_month - timedelta(days=1)
                first_day_last_month = last_day_last_month.replace(day=1)
                self.start_date = first_day_last_month.strftime("%Y-%m-%d")
                self.end_date = last_day_last_month.strftime("%Y-%m-%d")
                self.period_name = last_day_last_month.strftime("%Y年%m月")
                self.year = last_day_last_month.year
                self.period = last_day_last_month.month
            else:
                first_day_this_month = today.replace(day=1)
                self.start_date = first_day_this_month.strftime("%Y-%m-%d")
                self.end_date = today.strftime("%Y-%m-%d")
                self.period_name = today.strftime("%Y年%m月")
                self.year = today.year
                self.period = today.month

        # 默认不写死任何组织编码/公司名；登录后按 --org 或系统组织动态解析
        self.target_settle_org_numbers = []
        self.default_settle_org_id_map = {}
        self.sale_org_numbers = []
        self.inventory_org_number = None
        self.account_book_number = ""
        self.bill_configs = self._build_bill_configs()
        self.report_configs = self._build_report_configs()
        self._attach_official_fields_to_configs()

        print(f"查询{self.period_name}数据，日期范围: {self.start_date} 至 {self.end_date}")

    def _build_bill_configs(self):
        sale_org_filter = self._build_org_filter("FSaleOrgId.FNumber", self.sale_org_numbers)
        settle_org_filter = self._build_org_filter("FSETTLEORGID.FNumber", self.target_settle_org_numbers)
        pay_org_filter = self._build_org_filter("FPAYORGID.FNumber", self.target_settle_org_numbers)
        purchase_org_filter = self._build_org_filter("FPurchaseOrgId.FNumber", self.target_settle_org_numbers)

        return [
            {
                "form_id": "SAL_OUTSTOCK",
                "bill_name": "销售出库单",
                "field_keys": "FBillNo,FDate,FCustomerID.FName,FBillTypeID.FName,FSaleDeptID.FName,FSalesManID.FName,FNote,FMaterialID.FName,FStockID.FName,FEntryTaxAmount,FAmount,FAllAmount,FEntryCostAmount",
                "filter_string": f"{sale_org_filter} AND FDate>='{self.start_date}' AND FDate<='{self.end_date}' AND FDocumentStatus='C'",
                "columns": ["单据编号", "日期", "客户", "单据类型", "销售部门", "销售员", "备注", "物料名称", "仓库", "税额", "金额", "价税合计", "总成本"],
            },
            {
                "form_id": "SAL_SaleOrder",
                "bill_name": "销售订单",
                "field_keys": "FDate,FBillTypeID.FName,FBillNo,FDocumentStatus,FCustId.FName,FSaleDeptId.FName,FSalerId.FName,FCreatorId.FName,FCloseStatus,FMaterialId.FNumber,FMaterialName,FUnitID.FName,FQty,FPrice,FEntryTaxAmount,FAllAmount,FDeliveryDate",
                "filter_string": f"{sale_org_filter} AND FDate>='{self.start_date}' AND FDate<='{self.end_date}'",
                "columns": ["日期", "单据类型", "单据编号", "单据状态", "客户", "销售部门", "销售员", "创建人", "关闭状态", "物料编码", "物料名称", "销售单位", "销售数量", "单价", "税额", "价税合计", "要货日期"],
            },
            {
                "form_id": "SAL_RETURNSTOCK",
                "bill_name": "销售退货单",
                "field_keys": "FBillNo,FDate,FRetcustId.FName,FBillTypeID.FName,FSaledeptid.FName,FSalesManId.FName,FHeadNote,FMaterialId.FName,FStockId.FName,FEntryTaxAmount,FAmount,FAllAmount,FEntryCostAmount",
                "filter_string": f"{sale_org_filter} AND FDate>='{self.start_date}' AND FDate<='{self.end_date}' AND FDocumentStatus='C'",
                "columns": ["单据编号", "日期", "退货客户", "单据类型", "销售部门", "销售员", "备注", "物料名称", "仓库", "税额", "金额", "价税合计", "总成本"],
            },
            {
                "form_id": "AR_receivable",
                "bill_name": "应收单",
                "field_keys": "FBillTypeID.FName,FBillNo,FDATE,FCUSTOMERID.FName,FSALEORGID.FName,FSALEDEPTID.FName,FMATERIALID.FName,FTAXAMOUNTFOR_D,FNoTaxAmountFor_D,FALLAMOUNTFOR_D,FCreatorId.FName,FAR_Remark",
                "filter_string": f"{self._build_org_filter('FSALEORGID.FNumber', self.target_settle_org_numbers)} AND FDATE>='{self.start_date}' AND FDATE<='{self.end_date}' AND FDocumentStatus='C'",
                "columns": ["单据类型", "单据编号", "业务日期", "客户", "销售组织", "销售部门", "物料名称", "税额", "不含税金额", "价税合计", "创建人", "备注"],
            },
            {
                "form_id": "AP_Payable",
                "bill_name": "应付单",
                "field_keys": "FBillTypeID.FName,FDATE,FSUPPLIERID.FName,FBillNo,FSETTLEORGID.FName,FPURCHASEDEPTID.FName,FMATERIALID.FName,FCostName,FCOSTDEPARTMENTID.FName,FCreatorId.FName,FTAXAMOUNTFOR_D,FNOTAXAMOUNT_D,FALLAMOUNT_D,FAP_Remark",
                "filter_string": f"{settle_org_filter} AND FDATE>='{self.start_date}' AND FDATE<='{self.end_date}' AND FDOCUMENTSTATUS='C'",
                "columns": ["单据类型", "业务日期", "供应商", "单据编号", "结算组织", "采购部门", "物料名称", "费用项目名称", "费用承担部门", "创建人", "税额", "不含税金额本位币", "价税合计本位币", "备注"],
            },
            {
                "form_id": "PUR_PurchaseOrder",
                "bill_name": "采购订单",
                "field_keys": "FBillNo,FDate,FSupplierId.FName,FDocumentStatus,FPurchaseOrgId.FName,FPurchaserId.FName,FCreatorId.FName,FCloseStatus,F_TJKT_ChangeReason_re5,FMaterialId.FNumber,FMaterialName,FUnitId.FName,FQty,FDeliveryDate,FPrice,FEntryTaxAmount,FAllAmount,FGiveAway",
                "filter_string": f"{purchase_org_filter} AND FDate>='{self.start_date}' AND FDate<='{self.end_date}'",
                "columns": ["单据编号", "采购日期", "供应商", "单据状态", "采购组织", "采购员", "创建人", "关闭状态", "摘要", "物料编码", "物料名称", "采购单位", "采购数量", "交货日期", "单价", "税额", "价税合计", "是否赠品"],
            },
            {
                "form_id": "IV_ReceivedInvoice",
                "bill_name": "收票单",
                "field_keys": "FBillNo,FIVCODE,FIVNUMBER,FPURNAME,FSALENAME,FSUMAMOUNT,FSUMTAXAMOUNT,FSUMALLAMOUNT,FOPENDATE,FSTATUS,FLINKIVNUMBER,FLINKBILLTYPE,FLINKBILLDATE",
                "filter_string": f"{settle_org_filter} AND FOPENDATE>='{self.start_date}' AND FOPENDATE<='{self.end_date}'",
                "columns": ["单据编号", "发票代码", "发票号码", "购货方名称", "销售方名称", "不含税额", "税额", "价税合计", "开票日期", "发票状态", "关联单据编号", "关联单据类型", "关联单据日期"],
            },
            {
                "form_id": "ER_ExpenseRequest",
                "bill_name": "费用申请单",
                "field_keys": "FBillNo,FDate,FStaffID.FName,FDeptID.FName,FOrgID.FName,FExpenseItemID.FName,FReason,FIsBorrow,FDocumentStatus,FCloseStatus,FOrgAmount,FCheckedOrgAmount",
                "filter_string": f"{self._build_org_filter('FOrgID.FNumber', self.target_settle_org_numbers)} AND FDate>='{self.start_date}' AND FDate<='{self.end_date}'",
                "columns": ["单据编号", "申请日期", "申请人", "申请部门", "申请组织", "费用项目", "事由", "申请借款", "单据状态", "关闭状态", "申请金额", "核定金额"],
            },
            {
                "form_id": "ER_ExpReimbursement",
                "bill_name": "费用报销单",
                "field_keys": "FBillTypeID.FName,FRealPay,FBillNo,FCausa,FDate,FProposerID.FName,FRequestDeptID.FName,FOrgID.FName,FRequestType,FExpID.FName,FDocumentStatus,FExpenseAmount,FRequestAmount,FPayedAmount,FRefundedAmount,FBorrowAmount,FOffsetAmount,FReimbNotPayAmount",
                "filter_string": f"{self._build_org_filter('FOrgID.FNumber', self.target_settle_org_numbers)} AND FDate>='{self.start_date}' AND FDate<='{self.end_date}' AND FCancelStatus='A'",
                "columns": ["单据类型", "实报实付", "单据编号", "事由", "申请日期", "申请人", "申请部门", "申请组织", "退款/付款", "费用项目", "单据状态", "申请报销金额", "申请退/付款金额", "已付款金额", "已退款金额", "冲借款金额", "冲销金额", "报销未付款金额"],
            },
            {
                "form_id": "ER_ExpenseRequest_Travel",
                "bill_name": "出差申请单",
                "field_keys": "FBillNo,FDate,FReason,FExpenseItemID.FName,FStaffID.FName,FDeptID.FName,FOrgID.FName,FIsBorrow,FOrgAmount,FDocumentStatus,FCheckedOrgAmount,FCloseStatus",
                "filter_string": f"{self._build_org_filter('FOrgID.FNumber', self.target_settle_org_numbers)} AND FDate>='{self.start_date}' AND FDate<='{self.end_date}' AND FCancelStatus='A'",
                "columns": ["单据编号", "申请日期", "事由", "费用项目", "申请人", "申请部门", "申请组织", "申请借款", "申请金额", "单据状态", "核定金额", "关闭状态"],
            },
            {
                "form_id": "ER_ExpReimbursement_Travel",
                "bill_name": "差旅费报销单",
                "field_keys": "FBillTypeID.FName,FRealPay,FBillNo,FCausa,FDate,FProposerID.FName,FRequestDeptID.FName,FOrgID.FName,FRequestType,FExpID.FName,FDocumentStatus,FExpenseAmount,FExpenseOrgId.FName,FRequestAmount,FPayedAmount,FReimbNotPayAmount,FRemark",
                "filter_string": f"{self._build_org_filter('FOrgID.FNumber', self.target_settle_org_numbers)} AND FDate>='{self.start_date}' AND FDate<='{self.end_date}' AND FCancelStatus='A'",
                "columns": ["单据类型", "实报实付", "单据编号", "事由", "申请日期", "申请人", "申请部门", "申请组织", "退款/付款", "费用项目", "单据状态", "申请报销金额", "费用承担组织", "申请退/付款金额", "已付款金额", "报销未付款金额", "备注"],
            },
            {
                "form_id": "CN_PAYAPPLY",
                "bill_name": "付款申请单",
                "field_keys": "FBILLTYPEID.FName,FBillNo,FDATE,FCONTACTUNIT.FName,FCURRENCYID.FName,FPAYAMOUNTFOR_H,FAPPLYAMOUNTFOR_H,FSETTLECUR.FName,FSETTLEORGID.FName,FCREATORID.FName,FDEPARTMENT.FName,FDOCUMENTSTATUS,FCLOSESTATUS,FPAYPURPOSEID.FName,FENDDATE,FCOSTID.FName,FDescription",
                "filter_string": f"{self._build_org_filter('FSETTLEORGID.FNumber', self.target_settle_org_numbers)} AND FDATE>='{self.start_date}' AND FDATE<='{self.end_date}' AND FCANCELSTATUS='A'",
                "columns": ["单据类型", "单据编号", "申请日期", "往来单位", "币别", "应付金额", "申请付款金额", "结算币别", "结算组织", "创建人", "部门", "单据状态", "关闭状态", "付款用途", "到期日", "费用项目", "备注"],
            },
            {
                "form_id": "AP_PAYBILL",
                "bill_name": "付款单",
                "field_keys": "FBillTypeID.FName,FBillNo,FDATE,FCONTACTUNITTYPE,FCONTACTUNIT.FName,FREMARK,FSETTLETYPEID.FName,FPURPOSEID.FName,FPAYORGID.FName,FCOSTID.FName,FEXPENSEDEPTID_E.FName,FHANDLINGCHARGEFOR,FREALPAYAMOUNTFOR_D",
                "filter_string": f"{pay_org_filter} AND FDATE>='{self.start_date}' AND FDATE<='{self.end_date}' AND FDOCUMENTSTATUS='C'",
                "columns": ["单据类型", "单据编号", "业务日期", "往来单位类型", "往来单位", "备注", "结算方式", "付款用途", "付款组织", "费用项目", "费用承担部门", "手续费", "表体-实付金额"],
            },
            {
                "form_id": "AR_RECEIVEBILL",
                "bill_name": "收款单",
                "field_keys": "FBillTypeID.FName,FBillNo,FDATE,FCONTACTUNITTYPE,FSETTLETYPEID.FName,FPURPOSEID.FName,FPAYORGID.FName,FSALEDEPTID.FName,FCONTACTUNIT.FName,FREMARK,FHANDLINGCHARGEFOR,FREALRECAMOUNTFOR_D",
                "filter_string": f"{pay_org_filter} AND FDATE>='{self.start_date}' AND FDATE<='{self.end_date}' AND FDOCUMENTSTATUS='C'",
                "columns": ["单据类型", "单据编号", "业务日期", "往来单位类型", "结算方式", "收款用途", "收款组织", "销售部门", "往来单位", "备注", "手续费", "表体-实收金额"],
            },
            {
                "form_id": "AP_REFUNDBILL",
                "bill_name": "付款退款单",
                "field_keys": "FBillTypeID.FName,FBillNo,FDATE,FCONTACTUNIT.FName,FPAYUNIT.FName,FSETTLETYPEID.FName,FPURPOSEID.FName,FREALREFUNDAMOUNTFOR_D,FPAYORGID.FName,FDepartment.FName,FEXPENSEDEPTID_E.FName,FCOSTID.FName,FREMARK",
                "filter_string": f"{pay_org_filter} AND FDATE>='{self.start_date}' AND FDATE<='{self.end_date}' AND FDOCUMENTSTATUS='C'",
                "columns": ["单据类型", "单据编号", "业务日期", "往来单位", "付款单位", "结算方式", "原付款用途", "表体-实退金额", "付款组织", "部门", "费用承担部门", "费用项目", "备注"],
            },
            {
                "form_id": "AR_REFUNDBILL",
                "bill_name": "收款退款单",
                "field_keys": "FBillTypeID.FName,FBillNo,FDATE,FCONTACTUNIT.FName,FSETTLETYPEID.FName,FPURPOSEID.FName,FREFUNDAMOUNTFOR_E,FPAYORGID.FName,FSALEDEPTID.FName,FREMARK",
                "filter_string": f"{pay_org_filter} AND FDATE>='{self.start_date}' AND FDATE<='{self.end_date}' AND FDOCUMENTSTATUS='C'",
                "columns": ["单据类型", "单据编号", "业务日期", "往来单位", "结算方式", "原收款用途", "表体-实退金额", "付款组织", "销售部门", "备注"],
            },
            {
                "form_id": "AP_OtherPayable",
                "bill_name": "其他应付单",
                "field_keys": "FBillTypeID.FName,FBillNo,FDATE,FCONTACTUNITTYPE,FCONTACTUNIT.FName,FTOTALAMOUNTFOR_H,FCOSTNAME,FDEPARTMENTID.FName,FSETTLEORGID.FName,FCreatorId.FName",
                "filter_string": f"{settle_org_filter} AND FDATE>='{self.start_date}' AND FDATE<='{self.end_date}' AND FDOCUMENTSTATUS='C'",
                "columns": ["单据类型", "单据编号", "业务日期", "往来单位类型", "往来单位", "总金额", "费用项目名称", "申请部门", "结算组织", "创建人"],
            },
            {
                "form_id": "AR_OtherRecAble",
                "bill_name": "其他应收单",
                "field_keys": "FBillTypeID.FName,FBillNo,FDATE,FCONTACTUNITTYPE,FCONTACTUNIT.FName,FAMOUNTFOR,FCOSTNAME,FDEPARTMENTID.FName,FSETTLEORGID.FName,FCreatorId.FName",
                "filter_string": f"{settle_org_filter} AND FDATE>='{self.start_date}' AND FDATE<='{self.end_date}' AND FDOCUMENTSTATUS='C'",
                "columns": ["单据类型", "单据编号", "业务日期", "往来单位类型", "往来单位", "总金额", "费用项目名称", "申请部门", "结算组织", "创建人"],
            },
            {
                "form_id": "AP_AdjustExchangeRate",
                "bill_name": "应付调汇单",
                "field_keys": "FBillNo,FCONTACTUNITTYPE,FCONTACTUNIT.FName,FBUSINESSDEPTID.FName,FDATE,FADJEXCAMOUNT",
                "filter_string": f"{settle_org_filter} AND FDATE>='{self.start_date}' AND FDATE<='{self.end_date}' AND FDOCUMENTSTATUS='C'",
                "columns": ["单据编号", "往来单位类型", "往来单位", "业务部门", "业务日期", "调汇金额"],
            },
        ]

    def _build_report_configs(self):
        inventory_org_number = self.inventory_org_number or (self.target_settle_org_numbers[0] if self.target_settle_org_numbers else "")

        return [
            {
                "form_id": "AP_SumReport",
                "report_name": "应付款汇总表",
                "field_keys": "FCONTACTUNITNUMBER,FCONTACTUNITNAME,FSETTLEORGNAME,FINITAMOUNT,FAMOUNT,FREALAMOUNT,FOFFAMOUNT,FLEFTAMOUNT",
                "model": {
                    "FCONTACTUNITTYPE": "供应商",
                    "FUSEDATE": "true",
                    "FBeginDate": self.start_date,
                    "FEndDate": self.end_date,
                    "FSettleOrgLst": "1",
                    "FOutSettle": "true",
                    "FInSettle": "false",
                },
                "columns": ["往来单位编码", "往来单位名称", "结算组织", "(本位币)期初余额", "(本位币)本期应付", "(本位币)本期付款", "(本位币)本期冲销额", "(本位币)期末余额"],
            },
            {
                "form_id": "AR_SumReport",
                "report_name": "应收款汇总表",
                "field_keys": "FCONTACTUNITNUMBER,FCONTACTUNITNAME,FSETTLEORGNAME,FINITAMOUNTFOR,FAMOUNTFOR,FREALAMOUNTFOR,FOFFAMOUNTFOR,FLEFTAMOUNTFOR",
                "model": {
                    "FCONTACTUNITTYPE": "客户",
                    "FUSEDATE": "true",
                    "FBeginDate": self.start_date,
                    "FEndDate": self.end_date,
                    "FSettleOrgLst": "",
                    "FOutSettle": "true",
                    "FInSettle": "false",
                },
                "columns": ["往来单位编码", "往来单位名称", "结算组织", "(原币)期初余额", "(原币)本期应收", "(原币)本期收款", "(原币)本期冲销额", "(原币)期末余额"],
            },
            {
                "form_id": "HS_INOUTSTOCKSUMMARYRPT",
                "report_name": "存货收发存汇总表",
                "field_keys": "FMATERIALBASEID,FMATERIALNAME,FMATERIALGROUP,FSTOCKId,FINITQty,FINITPrice,FINITAMOUNT,FRECEIVEQty,FRECEIVEPrice,FRECEIVEAmount,FSENDQty,FSENDPrice,FSENDAmount,FENDQty,FENDPrice,FENDAmount",
                "model": {
                    "FACCTGSYSTEMID": {"FNumber": "KJHSTX01_SYS"},
                    "FACCTGORGID": {"FNumber": inventory_org_number},
                    "FACCTPOLICYID": {"FNumber": "KJZC01_SYS"},
                    "FYear": str(self.year),
                    "FPeriod": str(self.period),
                    "FENDYEAR": str(self.year),
                    "FEndPeriod": str(self.period),
                    "FCOMBOTotalType": "不汇总",
                    "FDimType": "FMATERIALID,FSTOCKID",
                    "FIsDisplayPeriod": True,
                },
                "columns": ["物料编码", "物料名称", "物料分组", "仓库", "期初数量", "期初单价", "期初金额", "收入数量", "收入单价", "收入金额", "发出数量", "发出单价", "发出金额", "期末数量", "期末单价", "期末金额"],
            },
            {
                "form_id": "HS_NoDimInOutStockDetailRpt",
                "report_name": "存货收发存明细表",
                "field_keys": "FPERIOD,FBILLDATE,FBILLNO,FBUSINESSTYPE,FBillFormName,FMATERIALID,FMATERIALNAME,FRECEIVEQty,FRECEIVEPrice,FRECEIVEAmount,FSENDQty,FSENDPrice,FSENDAmount,FENDQty,FENDPrice,FENDAmount",
                "model": {
                    "FACCTGSYSTEMID": {"FNumber": "KJHSTX01_SYS"},
                    "FACCTGORGID": {"FNumber": inventory_org_number},
                    "FACCTPOLICYID": {"FNumber": "KJZC01_SYS"},
                    "FYear": str(self.year),
                    "FENDYEAR": str(self.year),
                    "FPeriod": str(self.period),
                    "FEndPeriod": str(self.period),
                },
                "columns": ["期间", "单据日期", "单据编号", "业务类型", "单据类型", "物料编码", "物料名称", "收入数量", "收入单价", "收入金额", "发出数量", "发出单价", "发出金额", "期末数量", "期末单价", "期末金额"],
            },
            {
                "form_id": "CN_FundPositionReport",
                "report_name": "资金头寸表",
                "field_keys": "FRowTypeName,FBankName,FBankAcctName,FBankAcctNo,FPAYORGNAME,FINNERACCTNAME,FINNERACCTNO,FForCurrencyName,FForLastBal,FForTodayIn,FForTodayOut,FForTodayBal,FLocalCurrencyName,FLocalLastBal,FLocalTodayIn,FLocalTodayOut,FLocalTodayBal,FInCount,FOutCount",
                "model": {
                    "FOrgId": [{"FNumber": number} for number in self.target_settle_org_numbers],
                    "FStartDate": f"{self.start_date} 00:00:00",
                    "FEndDate": f"{self.end_date} 00:00:00",
                    "FNotAudit": False,
                    "FInNOut": True,
                    "FMyCurrency": False,
                    "FCurrencySubTotal": False,
                    "FSettleOrgBox": False,
                    "FPAYORGIDBOX": True,
                    "FMyCurrencySum": False,
                    "FMyPayOrg": False,
                    "FGroupCash": False,
                    "FOrgOrAccount": "0",
                    "FAllCashAccount": True,
                    "FAllBankAccount": False,
                    "FIsShowCancelBankAcnt": False,
                    "FINCLUDEEMPTY": False,
                },
                "columns": ["资金类别", "银行", "账户名称", "银行账号", "收付组织", "内部账户名称", "内部账户", "原币币别", "原币期初余额", "原币本日收入", "原币本日支出", "原币本日余额", "本位币币别", "本位币期初余额", "本位币本日收入", "本位币本日支出", "本位币本日余额", "收入笔数", "支出笔数"],
            },
            {
                "form_id": "CN_BankDetailReport",
                "report_name": "银行存款流水账",
                "field_keys": "FBANKACNTNAME_D,FBANKACNTNAME_NAME,FDate,FBillNo,FDesc,FUser,FForCurrencyName,FForTodayIn,FForTodayOut,FForTodayBal,FContactUnitName,FPurposeName,FBILLTYPEIDNAME",
                "scheme_id": "6a2b6ac47d6c89",
                "model": self.build_bank_detail_report_model(),
                "columns": ["银行账号", "银行账户名称", "业务日期", "单据编号", "摘要", "制单人", "币别", "收入金额", "支出金额", "金额", "往来单位", "收付款用途", "单据类型"],
            },
            {
                "form_id": "SAL_OutStockInvoiceRpt",
                "report_name": "销售出库开票跟踪表",
                "field_keys": "FSALEORGNAME,FBILLNO,FBILLTYPENAME,FDate,FSALESNAME,FCUSTOMERNAME,FMATERIALNAME,FREALQTY,FPrice,FALLAMOUNT,FISFREE,FRECQTY,FRECAMOUNT,FWriteOffAmount,FINVOECEQTY,FINVOECEAMOUNT,FRECEIPTAMOUNT,FJSWRITEOFFAMOUNT,FChargeOffAmount",
                "org_id_model_field": "FSaleOrgId",
                "model": {
                    "FSaleOrgId": "",
                    "FMoneyType": {"FNumber": ""},
                    "FStartDate": self.start_date,
                    "FEndDate": self.end_date,
                    "FCustomerFrom": {"FNumber": ""},
                    "FCustomerTo": {"FNumber": ""},
                    "FSaleDeptFrom": {"FNUMBER": ""},
                    "FSaleDeptTo": {"FNUMBER": ""},
                    "FMaterialFrom": {"FNumber": ""},
                    "FMaterialTo": {"FNumber": ""},
                    "FFormStatus": "C",
                    "FIsIncludeSerMat": "false",
                    "FSuite": "",
                    "FSettleOrgList": "",
                },
                "columns": ["销售组织", "单据编号", "单据类型", "日期", "销售员", "客户名称", "物料名称", "数量", "单价", "金额", "是否赠品", "应收数量", "应收金额", "调整金额", "开票数量", "开票金额", "结算金额", "结算调整金额", "特殊冲销金额"],
            },
            {
                "form_id": "PUR_PurchaseOrderDetailRpt",
                "report_name": "采购订单执行明细表",
                "field_keys": "FPurchaseOrgId,FBillNo,FDate,FSUPPLIERNAME,FMATERIALNAME,FDELIVERYDATE,FCurrencyId,FOrderQty,FOrderAmount,FReceiveQty,FReceiveAmount,FImportQty,FImportAmount,FReturnQty,FReturnAmount,FPAYQTY,FPAYAMOUNT,FPREINVOICEQTY,FPREINVOICEAMOUNT,FINVOICEQTY,FINVOICEAMOUNT,FRECPAYBILLAMOUNT,FPAYBILLAMOUNT,FSETADJAMOUNT,FPAYWRITOFFAMOUNT,FSPEWOFFAMOUNT",
                "org_id_model_field": "FPurchaseOrgIdList",
                "model": {
                    "FPurchaseOrgIdList": "",
                    "FOrderStartDate": self.start_date,
                    "FOrderEndDate": self.end_date,
                    "FBeginSupplierId": {"FNumber": ""},
                    "FEndSupplierId": {"FNumber": ""},
                    "FBeginBillNumber": "",
                    "FEndBillNumber": "",
                    "FBeginMaterialId": {"FNumber": ""},
                    "FEndMaterialId": {"FNumber": ""},
                    "FBeginPurchaser": {"FNumber": ""},
                    "FEndFPurchaser": {"FNumber": ""},
                    "FBusinessType": "",
                    "FDocumentStatus": "C",
                    "FLineStatus": "A",
                },
                "columns": ["采购组织", "订单编号", "日期", "供应商名称", "物料名称", "交货日期", "结算币别", "订货数量", "价税合计", "收料数量", "收料金额", "入库数量", "入库金额", "退料数量", "退料金额", "应付数量", "应付金额", "先开票数量", "先开票金额", "开票数量", "开票金额", "预付金额", "已结算金额", "结算调整金额", "付款核销金额", "特殊冲销金额"],
            },
            self._build_kds_report_config("财务报表", "BBMB0001", inventory_org_number),
            {
                "form_id": "GL_RPT_AccountBalance",
                "report_name": "科目余额表",
                "field_keys": "FBALANCEID,FBALANCENAME,FDETAILNUMBER,FDETAILNAME,FBEGINDEBITLOCAL,FBEGINCREDITLOCAL,FDEBITLOCAL,FCREDITLOCAL,FYTDDEBITLOCAL,FYTDCREDITLOCAL,FENDDEBITLOCAL,FENDCREDITLOCAL",
                "scheme_id": "69c396dfde2072",
                "model": {
                    "FACCTBOOKID": {"FNumber": self.account_book_number},
                    "FCURRENCY": "0",
                    "FSTARTYEAR": str(self.year),
                    "FSTARTPERIOD": str(self.period),
                    "FENDYEAR": str(self.year),
                    "FENDPERIOD": str(self.period),
                    "FBALANCELEVEL": "3",
                    "FSHOWDETAIL": True,
                    "FFORBIDBALANCE": True,
                    "FNOTPOSTVOUCHER": True,
                    "FDEBITORCREDIT": False,
                    "FBALANCEZERO": True,
                    "FNOBUSINESS": False,
                    "FPERIODNOBALANCE": True,
                    "FYEARNOBALANCE": True,
                    "FSHOWFULLNAME": True,
                    "FDETAILSHOWACCT": True,
                    "FSHOWDETAILONLY": False,
                    "FEXCLUDEADJUSTVCH": False,
                    "FFLEXDEBITORCREDIT": False,
                    "FSHOWFLEXBYCOL": False,
                },
                "columns": ["科目编码", "科目名称", "核算维度编码", "核算维度名称", "期初余额-本位币（借）", "期初余额-本位币（贷）", "本期发生-本位币（借）", "本期发生-本位币（贷）", "本年累计-本位币（借）", "本年累计-本位币（贷）", "期末余额-本位币（借）", "期末余额-本位币（贷）"],
            },
        ]

    def _build_kds_report_config(self, report_name, report_number, org_number):
        financial_report_config = (self.kingdee_config or {}).get("financial_report", {}) or {}
        cycle_type = int(financial_report_config.get("CycleType", 4))
        return {
            "form_id": "KDS_ReportData",
            "report_name": report_name,
            "api_type": "kds_report",
            "model": {
                "ReportType": int(financial_report_config.get("ReportType", 1)),
                "ReportNumber": financial_report_config.get("ReportNumber", report_number),
                "AcctSystemNumber": financial_report_config.get("AcctSystemNumber", "KJHSTX01_SYS"),
                "AcctPolicyNumber": financial_report_config.get("AcctPolicyNumber", "KJZC01_SYS"),
                "OrgNumber": org_number,
                "CurrencyNumber": financial_report_config.get("CurrencyNumber", "PRE001"),
                "CurrUnitNumber": financial_report_config.get("CurrUnitNumber", "JEDW01_SYS"),
                "CycleType": cycle_type,
                "Year": int(financial_report_config.get("Year", self.year)),
                "Period": int(financial_report_config.get("Period", self._report_period_for_cycle(cycle_type))),
                "DataType": "Json",
                "ResultType": "0",
            },
            "columns": None,
        }

    def _report_period_for_cycle(self, cycle_type):
        if cycle_type == 5:
            return (self.period - 1) // 3 + 1
        if cycle_type == 6:
            return 1 if self.period <= 6 else 2
        if cycle_type == 7:
            return 1
        return self.period

    def _resolve_org_scope_after_login(self):
        if self.requested_org_numbers and self.requested_org_numbers != ["all"]:
            resolved_org_numbers = self.requested_org_numbers
        else:
            all_orgs = self.get_all_organizations()
            resolved_org_numbers = [o.get("number") for o in all_orgs if o.get("number")]
            resolved_org_numbers = [n for n in resolved_org_numbers if n]
            if self.requested_org_numbers == ["all"] and not resolved_org_numbers:
                raise RuntimeError("未能从金蝶查询到组织列表，无法使用 --org all")

        self.target_settle_org_numbers = resolved_org_numbers
        self.sale_org_numbers = list(resolved_org_numbers)
        self.inventory_org_number = resolved_org_numbers[0] if resolved_org_numbers else None
        self.account_book_number = self.resolve_account_book_number(self.inventory_org_number)
        self.bill_configs = self._build_bill_configs()
        self.report_configs = self._build_report_configs()
        self._attach_official_fields_to_configs()

    def _normalize_only(self, only):
        if not only:
            return None
        if isinstance(only, str):
            parts = [p.strip() for p in only.split(",") if p.strip()]
        else:
            parts = [str(p).strip() for p in (only or []) if str(p).strip()]
        lowered = {p.lower() for p in parts}
        return lowered or None

    def _parse_extra_fields(self, extra_fields):
        """解析 --fields，格式：导出项:字段1,字段2;另一个导出项:字段3。"""
        parsed = {}
        if not extra_fields:
            return parsed
        raw = str(extra_fields).strip()
        if not raw:
            return parsed
        for group in re.split(r"[;；]", raw):
            if not group.strip():
                continue
            if ":" in group:
                target, fields_part = group.split(":", 1)
            elif "：" in group:
                target, fields_part = group.split("：", 1)
            else:
                target, fields_part = "*", group
            target = target.strip().lower() or "*"
            fields = [f.strip() for f in re.split(r"[,，]", fields_part) if f.strip()]
            if fields:
                parsed.setdefault(target, []).extend(fields)
        return parsed

    def _official_doc_name_for_config(self, config):
        return config.get("official_doc") or config.get("bill_name") or config.get("report_name")

    def _load_official_fields(self, doc_name):
        if not doc_name:
            return {}
        if doc_name in self.official_field_cache:
            return self.official_field_cache[doc_name]

        path = os.path.join(self.official_fields_dir, f"{doc_name}.txt")
        fields = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        match = re.search(r"\s*([^：:]+)[：:]\s*([A-Za-z_][A-Za-z0-9_.]*)", line)
                        if not match:
                            continue
                        name = match.group(1).strip()
                        key = match.group(2).strip()
                        if name and key:
                            fields[name] = key
                            fields[key.upper()] = key
            except Exception as e:
                print(f"  [WARN] 读取官方字段说明失败 {path}: {e}")

        self.official_field_cache[doc_name] = fields
        return fields

    def _attach_official_fields_to_configs(self):
        for config in self.bill_configs + self.report_configs:
            doc_name = self._official_doc_name_for_config(config)
            config["official_fields"] = self._load_official_fields(doc_name)

    def _append_extra_field_keys(self, config, field_keys):
        if not self.requested_extra_fields:
            return field_keys

        names = []
        for target in ("*", config.get("form_id", "").lower(), config.get("bill_name", "").lower(), config.get("report_name", "").lower()):
            names.extend(self.requested_extra_fields.get(target, []))
        if not names:
            return field_keys

        official_fields = config.get("official_fields") or {}
        keys = [k.strip() for k in str(field_keys or "").split(",") if k.strip()]
        key_set = {k.upper() for k in keys}
        for name in names:
            key = official_fields.get(name) or official_fields.get(name.upper())
            if not key and re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", name):
                key = name
            if not key:
                print(f"  [WARN] {config.get('bill_name') or config.get('report_name')} 未找到官方字段：{name}")
                continue
            if key.upper() not in key_set:
                keys.append(key)
                key_set.add(key.upper())
                print(f"  -> 已追加查询字段 {name}: {key}（默认不输出到Excel）")
        return ",".join(keys)

    def _parse_org_numbers(self, org_numbers):
        if isinstance(org_numbers, str):
            raw = org_numbers.strip()
            if raw.lower() == "all":
                return ["all"]
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            return parts
        return [str(x).strip() for x in (org_numbers or []) if str(x).strip()]

    def _build_org_filter(self, field_name, org_numbers):
        org_numbers = [str(x).strip() for x in (org_numbers or []) if str(x).strip()]
        if not org_numbers:
            return "1=1"
        if len(org_numbers) == 1:
            return f"{field_name}='{org_numbers[0]}'"
        in_values = ",".join([f"'{n}'" for n in org_numbers])
        return f"{field_name} IN ({in_values})"

    def resolve_settle_org_ids_by_numbers(self, org_numbers, default_map=None):
        """根据组织编码解析结算组织内码，并返回逗号拼接字符串。"""
        default_map = default_map or {}
        org_id_map = dict(default_map)

        need_query_numbers = [number for number in org_numbers if number not in org_id_map]

        if need_query_numbers:
            url = self.base_url + "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
            in_values = ",".join([f"'{number}'" for number in need_query_numbers])
            data = {
                "FormId": "AP_Payable",
                "FieldKeys": "FSETTLEORGID,FSETTLEORGID.FNumber,FSETTLEORGID.FName",
                "FilterString": f"FSETTLEORGID.FNumber IN ({in_values})",
                "OrderString": "",
                "TopRowCount": 0,
                "StartRow": 0,
                "Limit": 2000,
            }
            payload = {"formid": "AP_Payable", "data": json.dumps(data, ensure_ascii=False)}

            try:
                response = self.session.post(url, json=payload, timeout=60)
                if response.status_code == 200:
                    result = response.json()
                    if isinstance(result, list):
                        for row in result:
                            if not isinstance(row, list) or len(row) < 2:
                                continue
                            org_id = str(row[0]).strip()
                            org_number = str(row[1]).strip()
                            if org_id and org_number and org_number not in org_id_map:
                                org_id_map[org_number] = org_id
                else:
                    print(f"  [WARN] 组织内码查询失败，状态码: {response.status_code}")
            except Exception as e:
                print(f"  [WARN] 组织内码查询异常: {e}")

        settle_org_ids = [org_id_map[number] for number in org_numbers if number in org_id_map and org_id_map[number]]
        settle_org_lst = ",".join(settle_org_ids)
        print(f"  -> 结算组织内码映射: {org_id_map}")
        print(f"  -> FSettleOrgLst: {settle_org_lst or '[空]'}")
        return settle_org_lst

    def resolve_account_book_number(self, org_number):
        """根据组织编码推断主账簿编码。"""
        if not org_number:
            return ""
        configured_books = (self.kingdee_config or {}).get("account_book_numbers", {}) or {}
        if org_number in configured_books:
            return str(configured_books[org_number]).strip()
        configured_book = (self.kingdee_config or {}).get("account_book_number", "")
        if configured_book:
            return str(configured_book).strip()

        url = self.base_url + "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
        data = {
            "FormId": "BD_AccountBook",
            "FieldKeys": "FBOOKID,FNumber,FName",
            "FilterString": "",
            "OrderString": "",
            "TopRowCount": 0,
            "StartRow": 0,
            "Limit": 200,
        }
        try:
            response = self.session.post(url, json={"formid": "BD_AccountBook", "data": json.dumps(data, ensure_ascii=False)}, timeout=60)
            rows = response.json() if response.status_code == 200 else []
            for row in rows:
                if not isinstance(row, list) or len(row) < 3:
                    continue
                number = str(row[1]).strip()
                name = str(row[2]).strip()
                if org_number in name:
                    print(f"  -> 科目余额表账簿: {number} {name}")
                    return number
            if len(rows) == 1 and isinstance(rows[0], list) and len(rows[0]) >= 2:
                return str(rows[0][1]).strip()
            non_group_books = [row for row in rows if isinstance(row, list) and len(row) >= 3 and "集团" not in str(row[2])]
            if len(non_group_books) == 1:
                return str(non_group_books[0][1]).strip()
        except Exception as e:
            print(f"  [WARN] 账簿编码查询异常: {e}")
        return ""

    def build_ap_sum_report_model(self, settle_org_lst):
        """构建应付款汇总表Model。"""
        return {
            "FAffiliation": {"FNAME": ""},
            "FSTARTYEAR": str(self.year),
            "FENDYEAR": str(self.year),
            "FCONTACTUNITTYPE": "BD_Supplier",
            "FSTARTPERIOD": str(self.period),
            "FENDPERIOD": str(self.period),
            "FCONTACTUNITFrom": {"FNumber": ""},
            "FUSEDATE": "true",
            "FSettleOrgLst": settle_org_lst,
            "FCONTACTUNITTo": {"FNumber": ""},
            "FAccountSystem": {"FNumber": ""},
            "FInSettle": "true",
            "FOutSettle": "true",
            "FUSEPERIOD": "",
            "FNoShowForNoLeft": "false",
            "FNoShowForNoOccur": "false",
            "FNOAUDIT": "false",
            "FEndDate": self.end_date,
            "FBeginDate": self.start_date,
            "FNoShowForBoth": "false",
            "FCurrencyFrom": [{"FNumber": ""}],
            "FIncludePayEvaluate": "false",
            "FIncludePayEvaluate_New": "false",
            "FDEFAULTACCTCALENDARID": 0,
            "FOnlyShowPayEvaluate": "false",
            "FOnlyShowPayEvaluate_New": "false",
            "FShowLocal": "true",
            "FShowSumLocal": "false",
            "FNoPrePayment": "false",
            "FOnlyShowPrePayment": "false",
            "FShowAmountInCost": "false",
            "FCONTACTUNITMUL": "",
            "FMULCONTACT": "false",
            "FPRESETBASE1": [{"FNumber": ""}],
            "FPRESETBASE2": [{"FNumber": ""}],
            "FGROUPSUPPLIER": "false",
            "FPERIODAMOUNT": -999999999,
            "FTOPERIODAMOUNT": 999999999,
            "FCheckPeriod": "false",
            "FShowMatchBill": "true",
            "FDateRadioGrp": "",
        }

    def build_ar_sum_report_model(self, settle_org_lst):
        """构建应收款汇总表Model。"""
        return {
            "FAffiliation": {"FNAME": ""},
            "FSTARTYEAR": str(self.year),
            "FENDYEAR": str(self.year),
            "FCONTACTUNITTYPE": "BD_Customer",
            "FSTARTPERIOD": str(self.period),
            "FENDPERIOD": str(self.period),
            "FCONTACTUNITFrom": {"FNumber": ""},
            "FUSEDATE": "true",
            "FSettleOrgLst": settle_org_lst,
            "FCONTACTUNITTo": {"FNumber": ""},
            "FAccountSystem": {"FNumber": ""},
            "FInSettle": "true",
            "FOutSettle": "true",
            "FUSEPERIOD": "",
            "FNoShowForNoLeft": "false",
            "FNoShowForNoOccur": "false",
            "FNOAUDIT": "false",
            "FEndDate": self.end_date,
            "FBeginDate": self.start_date,
            "FNoShowForBoth": "false",
            "FCurrencyFrom": [{"FNumber": ""}],
            "FIncludePayEvaluate": "false",
            "FIncludePayEvaluate_New": "false",
            "FDEFAULTACCTCALENDARID": 0,
            "FOnlyShowPayEvaluate": "false",
            "FOnlyShowPayEvaluate_New": "false",
            "FShowLocal": "true",
            "FGroupCustomer": "false",
            "FShowSumLocal": "false",
            "FNoPreReceive": "false",
            "FOnlyShowPreReceive": "false",
            "FCONTACTUNITMUL": "",
            "FMULCONTACT": "false",
            "FPRESETBASE1": [{"FNumber": ""}],
            "FPRESETBASE2": [{"FNumber": ""}],
            "FEXCLUDEB2CAR": "false",
            "FPERIODAMOUNT": -999999999,
            "FTOPERIODAMOUNT": 999999999,
            "FCheckPeriod": "false",
            "FShowMatchBill": "true",
            "FDateRadioGrp": "",
        }

    def build_bank_detail_report_model(self):
        """构建银行存款流水账Model。"""
        bank_account_numbers = (self.kingdee_config or {}).get("bank_account_numbers", [])
        if isinstance(bank_account_numbers, str):
            bank_account_numbers = [n.strip() for n in bank_account_numbers.split(",") if n.strip()]
        else:
            bank_account_numbers = [str(n).strip() for n in (bank_account_numbers or []) if str(n).strip()]

        return {
            "FOrgID": [{"FNumber": number} for number in self.target_settle_org_numbers],
            "FGROUPBILLNO": False,
            "FBankAccountID": [{"FNumber": number} for number in bank_account_numbers],
            "FStartDate": f"{self.start_date} 00:00:00",
            "FEndDate": f"{self.end_date} 00:00:00",
            "FNotAudit": False,
            "FMyCurrency": False,
            "FSumMonth": False,
            "FSumYear": False,
            "FMyPayOrg": False,
            "FSettleOrgBox": False,
            "FPAYORGIDBOX": True,
            "FInnerPayOrgBox": False,
            "FSortRadioGroup": "0",
        }

    def _resolve_acctid(self):
        """acctid 为空时按 acct_name 自动解析（GetDataCenterList 免认证，登录前可用）。"""
        acctid = str(self.kingdee_config.get("acctid") or "").strip()
        if acctid:
            return acctid
        acct_name = str(self.kingdee_config.get("acct_name") or "").strip()
        if not acct_name:
            raise RuntimeError(
                "未配置账套：请填写 acctid，或填写 acct_name（账套名称）由脚本自动解析。\n"
                "  不确定账套 ID 时执行：python data_exporter.py --list-datacenters"
            )
        resolved, note = resolve_acctid_by_name(self.kingdee_config.get("base_url"), acct_name)
        if not resolved:
            raise RuntimeError(f"无法确定账套：{note}")
        print(f"  {note}")
        self.kingdee_config["acctid"] = resolved
        return resolved

    def login_kingdee(self):
        """登录金蝶云。

        失败时按错误原文给出「根因 + 下一步」；并对账号密码类失败做**防锁号**保护
        —— 金蝶密码连续错约 5 次会锁账号，所以判读为凭据问题时不自动重试。
        """
        if self._login_ok:
            return True
        if self._missing_config:
            print_config_guide("配置不完整：" + "、".join(self._missing_config))
            raise RuntimeError("缺少金蝶连接配置，已中止（配置方法见上方提示）。")

        acctid = self._resolve_acctid()
        ok, info = perform_login(
            self.session,
            self.base_url,
            acctid,
            self.kingdee_config.get("username"),
            self.kingdee_config.get("password"),
        )
        if ok:
            self._login_ok = True
            print("登录成功")
            return True

        self._login_fail_count += 1
        message = info.get("message") or ""
        hint = info.get("hint") or ""
        print(f"登录失败（第 {self._login_fail_count} 次）：{message}")
        if info.get("code") not in (None, ""):
            print(f"  错误码：{info['code']}")
        if hint:
            print(f"  → {hint}")

        credential_issue = any(word in f"{message}{hint}" for word in ("密码", "账号", "CheckPasswordPolicy"))
        if credential_issue and self._login_fail_count >= 2:
            raise RuntimeError(
                "已连续 2 次登录失败，停止重试以免账号被锁定（金蝶密码连续错约 5 次会锁号）。\n"
                "  请核对账号与密码（注意大小写、首尾空格）后再运行；忘记密码请找管理员重置。"
            )
        return False

    def get_all_organizations(self):
        """
        尝试从金蝶查询所有组织（用于 --org all / --list-orgs）。
        说明：不同环境的组织基础资料 FormId / 字段名可能有差异，这里做多种兜底尝试。
        """
        if not self.login_kingdee():
            raise RuntimeError("登录失败，无法查询组织列表")

        candidates = [
            ("ORG_Organizations", "FOrgId,FNumber,FName,FForbidStatus"),
            ("ORG_Organizations", "FOrgID,FNumber,FName,FForbidStatus"),
            ("BD_Organization", "FOrgId,FNumber,FName,FForbidStatus"),
            ("ORG_Organizations", "FNumber,FName"),
            ("BD_Organization", "FNumber,FName"),
        ]

        url = self.base_url + "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"

        for form_id, field_keys in candidates:
            data = {
                "formid": form_id,
                "data": json.dumps(
                    {
                        "FormId": form_id,
                        "FieldKeys": field_keys,
                        "FilterString": "",
                        "OrderString": "FNumber",
                        "TopRowCount": 0,
                        "StartRow": 0,
                        "Limit": 2000,
                    },
                    ensure_ascii=False,
                ),
            }
            try:
                resp = self.session.post(url, json=data, timeout=60)
                if resp.status_code != 200:
                    continue
                result = resp.json()
                if not isinstance(result, list):
                    continue

                rows = []
                for row in result:
                    if not isinstance(row, list) or len(row) < 2:
                        continue
                    number = str(row[1]).strip() if len(row) >= 2 else ""
                    name = str(row[2]).strip() if len(row) >= 3 else ""
                    org_id = str(row[0]).strip() if len(row) >= 1 else ""
                    rows.append({"id": org_id, "number": number, "name": name, "form_id": form_id})
                if any(r.get("number") for r in rows):
                    dedup = {}
                    for r in rows:
                        key = r.get("number") or r.get("name") or r.get("id")
                        if not key:
                            continue
                        dedup[key] = r
                    rows = list(dedup.values())
                    rows.sort(key=lambda x: x.get("number") or "")
                    return rows
            except Exception:
                continue

        raise RuntimeError(
            "查询组织列表失败：金蝶环境里的组织基础资料 FormId/字段可能与默认值不同。\n"
            "  已尝试：ORG_Organizations / BD_Organization。\n"
            "  可用 --inspect-fields ORG_Organizations 核对当前账套的实际字段；\n"
            "  若该账套用别的业务对象存组织，请反馈你的 FormId 以便补充默认清单。"
        )

    def get_bill_data_with_filter(self, form_id, field_keys, filter_string):
        """使用字段和过滤条件获取单据数据"""
        all_data = []
        start_row = 0
        limit = 2000

        url = self.base_url + "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"

        print("  正在获取数据...")

        while True:
            data = {
                "formid": form_id,
                "data": json.dumps(
                    {
                        "FormId": form_id,
                        "FieldKeys": field_keys,
                        "FilterString": filter_string,
                        "OrderString": "",
                        "TopRowCount": 0,
                        "StartRow": start_row,
                        "Limit": limit,
                    }
                ),
            }

            try:
                response = self.session.post(url, json=data, timeout=60)

                if response.status_code == 200:
                    result = response.json()

                    if isinstance(result, list) and len(result) > 0:
                        all_data.extend(result)
                        print(f"  已获取 {len(all_data)} 条数据...")

                        if len(result) < limit:
                            break

                        start_row += limit
                    else:
                        break
                else:
                    print(f"  API请求失败: {response.status_code}")
                    print(f"  响应内容: {response.text[:500]}")
                    break

            except Exception as e:
                print(f"  获取数据异常: {e}")
                import traceback

                traceback.print_exc()
                break

        print(f"  共获取到 {len(all_data)} 条数据")
        return all_data

    def get_report_data(self, form_id, field_keys, model, scheme_id=""):
        """使用GetSysReportData接口获取报表数据"""
        all_data = []
        start_row = 0
        limit = 10000

        url = self.base_url + "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.GetSysReportData.common.kdsvc"

        print("  正在获取报表数据...")

        while True:
            data = {
                "FieldKeys": field_keys,
                "SchemeId": scheme_id,
                "StartRow": start_row,
                "Limit": limit,
                "IsVerifyBaseDataField": "true",
                "FilterString": [],
                "Model": model,
            }

            payload = {"formid": form_id, "data": json.dumps(data, ensure_ascii=False)}

            try:
                response = self.session.post(url, json=payload, timeout=120)

                if response.status_code == 200:
                    result = response.json()

                    if not result.get("Result", {}).get("IsSuccess", False):
                        error_msg = result.get("Result", {}).get("Message", "未知错误")
                        print(f"  API返回错误: {error_msg}")
                        print(f"  调试信息 - 完整响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
                        break

                    rows = result.get("Result", {}).get("Rows", [])
                    row_count = result.get("Result", {}).get("RowCount", 0)

                    if rows and len(rows) > 0:
                        all_data.extend(rows)
                        print(f"  已获取 {len(all_data)} 条数据...")

                        if len(all_data) >= row_count or len(rows) < limit:
                            break

                        start_row += len(rows)
                    else:
                        break
                else:
                    print(f"  API请求失败: {response.status_code}")
                    print(f"  响应内容: {response.text[:500]}")
                    break

            except Exception as e:
                print(f"  获取报表数据异常: {e}")
                import traceback

                traceback.print_exc()
                break

        print(f"  共获取到 {len(all_data)} 条报表数据")
        return all_data

    def get_kds_report_data(self, model):
        """使用财务报表 GetReportData 接口获取报表数据。"""
        url = self.base_url + "Kingdee.BOS.KDS.ServiceFacade.ServicesStub.KDSReportAPIStub.GetReportData.common.kdsvc"
        payload = {"parameters": [json.dumps(model, ensure_ascii=False)]}

        print("  正在获取财务报表数据...")
        try:
            response = self.session.post(url, json=payload, timeout=120)
            if response.status_code != 200:
                print(f"  API请求失败: {response.status_code}")
                print(f"  响应内容: {response.text[:500]}")
                return []

            result = response.json()
            if isinstance(result, str):
                result = json.loads(result)
            if isinstance(result, dict) and str(result.get("status", "")).lower() in ("1", "false", "error"):
                print(f"  API返回错误: {result.get('message') or result}")
                return []
            return self._normalize_kds_report_result(result)
        except Exception as e:
            print(f"  获取财务报表数据异常: {e}")
            import traceback

            traceback.print_exc()
            return []

    def _normalize_kds_report_result(self, result):
        if isinstance(result, dict) and "result" in result:
            result = result.get("result")
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:
                    return [["报表结果", result]]

        spread_rows = self._extract_kds_spread_rows(result)
        if spread_rows:
            return spread_rows

        if isinstance(result, dict):
            for key in ("Rows", "rows", "Data", "data", "Result", "result"):
                value = result.get(key)
                if isinstance(value, list):
                    return value
            return [[k, v] for k, v in result.items()]
        if isinstance(result, list):
            return result
        return [["报表结果", result]]

    def _extract_kds_spread_rows(self, result):
        if not isinstance(result, dict):
            return []

        def walk(node):
            if isinstance(node, dict):
                if node.get("xtype") == "kdspread" and isinstance(node.get("data"), dict):
                    data = node["data"].get("data")
                    if isinstance(data, list) and data:
                        sheets = {}
                        for cells in data:
                            rows = self._kds_cells_to_rows(cells)
                            if not rows:
                                continue
                            title = str(rows[0][0]).strip() or f"报表{len(sheets) + 1}"
                            sheets[title[:31]] = rows
                        return sheets or []
                for value in node.values():
                    found = walk(value)
                    if found:
                        return found
            elif isinstance(node, list):
                for item in node:
                    found = walk(item)
                    if found:
                        return found
            return []

        cells = walk(result)
        if not cells:
            return []
        if isinstance(cells, dict):
            return cells

        return self._kds_cells_to_rows(cells)

    def _kds_cells_to_rows(self, cells):
        if not cells:
            return []
        max_row = max(int(cell[0]) for cell in cells if isinstance(cell, list) and len(cell) >= 3)
        max_col = max(int(cell[1]) for cell in cells if isinstance(cell, list) and len(cell) >= 3)
        rows = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
        for cell in cells:
            if not isinstance(cell, list) or len(cell) < 3:
                continue
            row_idx = int(cell[0])
            col_idx = int(cell[1])
            rows[row_idx][col_idx] = cell[2]

        while rows and all(str(v).strip() == "" for v in rows[-1]):
            rows.pop()
        return rows

    def parse_report_to_dataframe(self, data, columns=None, form_id=None):
        """将报表数据解析为 DataFrame"""
        if isinstance(data, dict):
            return {sheet_name: self.parse_report_to_dataframe(rows, columns=None, form_id=form_id) for sheet_name, rows in data.items()}

        if not isinstance(data, list) or len(data) == 0:
            if columns:
                return pd.DataFrame(columns=columns)
            return pd.DataFrame()

        if columns:
            df_columns = list(columns)
            if isinstance(data[0], (list, tuple)) and len(data[0]) > len(df_columns):
                df_columns.extend([f"__extra_field_{i}" for i in range(1, len(data[0]) - len(columns) + 1)])
            df = pd.DataFrame(data, columns=df_columns)
            output_columns = list(columns)
        else:
            df = pd.DataFrame(data)
            output_columns = None

        if form_id == "KDS_ReportData":
            return df

        # 过滤 AP/AR 汇总表中的“小计/合计”等行（小计可能出现在前两列）
        if form_id in ("AP_SumReport", "AR_SumReport") and len(df.columns) >= 2:
            first_col = df.columns[0]
            second_col = df.columns[1]
            for col in (first_col, second_col):
                df = df[~(df[col].astype(str).str.contains("小计", na=False, regex=False))]
                df = df[~(df[col].astype(str).str.contains("合计", na=False, regex=False))]

        for col in df.columns:
            if "日期" in str(col) or "Date" in str(col):
                try:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                    df[col] = df[col].dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

        exclude_columns = []
        if form_id in ("AP_SumReport", "AR_SumReport") and len(df.columns) >= 3:
            exclude_columns = [df.columns[0], df.columns[1], df.columns[2]]
        if form_id == "HS_NoDimInOutStockDetailRpt" and len(df.columns) >= 1:
            if df.columns[0] not in exclude_columns:
                exclude_columns.append(df.columns[0])
        df = self._coerce_numeric_like_columns(df, exclude_columns=exclude_columns)

        if form_id in ("AP_SumReport", "AR_SumReport"):
            numeric_candidates = df.columns[3:]
        elif form_id == "HS_INOUTSTOCKSUMMARYRPT":
            numeric_candidates = [c for c in df.columns if c not in ["物料编码", "物料名称", "物料分组", "仓库"]]
        elif form_id == "HS_NoDimInOutStockDetailRpt":
            numeric_candidates = [c for c in df.columns if c not in ["期间", "单据日期", "单据编号", "业务类型", "单据类型", "物料编码", "物料名称"]]
        elif form_id in ("SAL_OutStockInvoiceRpt", "PUR_PurchaseOrderDetailRpt"):
            numeric_candidates = [
                c
                for c in df.columns
                if c
                not in [
                    "销售组织",
                    "单据编号",
                    "单据类型",
                    "日期",
                    "销售员",
                    "客户名称",
                    "物料名称",
                    "是否赠品",
                    "采购组织",
                    "订单编号",
                    "供应商名称",
                    "交货日期",
                    "结算币别",
                ]
            ]
        elif form_id == "GL_RPT_AccountBalance":
            numeric_candidates = [c for c in df.columns if c not in ["科目编码", "科目名称", "核算维度编码", "核算维度名称"]]
            if "科目编码" in df.columns:
                df["科目编码"] = df["科目编码"].map(self._format_account_code)
        elif form_id == "CN_BankDetailReport":
            numeric_candidates = [c for c in df.columns if c in ["收入金额", "支出金额", "金额"]]
        else:
            numeric_candidates = []

        for col in numeric_candidates:
            if col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
                try:
                    df[col] = self._clean_numeric_series(df[col])
                except Exception:
                    pass

        if form_id == "PUR_PurchaseOrderDetailRpt":
            df = self._fill_purchase_order_detail_merged_headers(df)

        if output_columns:
            df = df[[col for col in output_columns if col in df.columns]]

        return df

    def _format_account_code(self, value):
        if pd.isna(value):
            return ""
        text = str(value).strip()
        if text.endswith(".0"):
            text = text[:-2]
        return text

    def _fill_purchase_order_detail_merged_headers(self, df):
        if df is None or df.empty or "订单编号" not in df.columns:
            return df

        header_columns = ["采购组织", "订单编号", "日期", "供应商名称"]
        header_columns = [col for col in header_columns if col in df.columns]
        if not header_columns:
            return df

        normalized_order_no = df["订单编号"].astype(str).str.strip()
        detail_value_columns = [
            col
            for col in ["物料名称", "订货数量", "价税合计", "收料数量", "入库数量", "应付数量", "开票数量", "已结算金额"]
            if col in df.columns
        ]

        if detail_value_columns:
            has_detail_values = df[detail_value_columns].astype(str).apply(lambda s: s.str.strip()).ne("").any(axis=1)
        else:
            has_detail_values = pd.Series(True, index=df.index)

        fill_mask = normalized_order_no.eq("") & has_detail_values
        filled_headers = df[header_columns].replace(r"^\s*$", pd.NA, regex=True).ffill()
        df.loc[fill_mask, header_columns] = filled_headers.loc[fill_mask, header_columns]
        return df

    def _clean_numeric_series(self, series):
        cleaned = self._normalize_numeric_text(series)
        return pd.to_numeric(cleaned, errors="coerce").fillna(0)

    def _normalize_numeric_text(self, series):
        if series is None:
            return series

        cleaned = series.astype(str)
        cleaned = cleaned.str.replace("\u00A0", "", regex=False)
        cleaned = cleaned.str.replace("\u3000", "", regex=False)
        cleaned = cleaned.str.replace(r"\s+", "", regex=True)
        cleaned = cleaned.str.strip()
        cleaned = cleaned.str.replace(",", "", regex=False)
        cleaned = cleaned.str.replace("，", "", regex=False)
        cleaned = cleaned.str.replace("￥", "", regex=False)
        cleaned = cleaned.str.replace("¥", "", regex=False)
        cleaned = cleaned.str.replace("$", "", regex=False)
        cleaned = cleaned.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
        cleaned = cleaned.str.replace(r"^（(.*)）$", r"-\1", regex=True)
        cleaned = cleaned.str.replace(r"^(\d+(?:\.\d+)?)-$", r"-\1", regex=True)

        cleaned = cleaned.replace(
            {
                "": None,
                "None": None,
                "nan": None,
                "NaN": None,
                "-": None,
                "—": None,
                "–": None,
            }
        )
        return cleaned

    def _coerce_numeric_like_columns(self, df, exclude_columns=None):
        if df is None or df.empty:
            return df

        exclude_columns = set(exclude_columns or [])
        for col in df.columns:
            if col in exclude_columns:
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                continue
            if not pd.api.types.is_object_dtype(df[col]):
                continue

            series = df[col]
            cleaned = self._normalize_numeric_text(series)
            non_empty = cleaned.dropna()
            if non_empty.empty:
                continue

            numeric = pd.to_numeric(non_empty, errors="coerce")
            if numeric.notna().mean() >= 0.7:
                df[col] = self._clean_numeric_series(series)

        return df

    def build_fund_position_output(self, df):
        column_map = {
            "银行": "银行",
            "原币期初余额": "(原币)期初余额",
            "原币本日收入": "(原币)本期收入",
            "原币本日支出": "(原币)本期支出",
            "原币本日余额": "(原币)本期余额",
            "收入笔数": "收入笔数",
            "支出笔数": "支出笔数",
        }

        output_columns = list(column_map.values())
        if df is None or df.empty:
            return pd.DataFrame(columns=output_columns)

        df_selected = pd.DataFrame()
        for src_col, dst_col in column_map.items():
            if src_col in df.columns:
                df_selected[dst_col] = df[src_col]
            else:
                df_selected[dst_col] = 0

        numeric_cols = [col for col in df_selected.columns if col != "银行"]
        for col in numeric_cols:
            df_selected[col] = self._clean_numeric_series(df_selected[col])

        summary = {col: 0 for col in df_selected.columns}
        summary["银行"] = "合计"
        for col in numeric_cols:
            summary[col] = df_selected[col].sum()

        df_selected = pd.concat([df_selected, pd.DataFrame([summary])], ignore_index=True)

        for col in ["收入笔数", "支出笔数"]:
            if col in df_selected.columns:
                df_selected[col] = pd.to_numeric(df_selected[col], errors="coerce").fillna(0).astype(int)

        return df_selected[output_columns]

    def parse_data_to_dataframe(self, data, columns, form_id=None):
        """将数据解析为DataFrame，添加列名"""
        if not isinstance(data, list) or len(data) == 0:
            return pd.DataFrame(columns=columns)

        df_columns = list(columns)
        if isinstance(data[0], (list, tuple)) and len(data[0]) > len(df_columns):
            df_columns.extend([f"__extra_field_{i}" for i in range(1, len(data[0]) - len(columns) + 1)])
        df = pd.DataFrame(data, columns=df_columns)

        date_columns = ["日期", "业务日期", "采购日期", "申请日期", "要货日期", "交货日期", "到期日", "开票日期", "关联单据日期"]
        for col in date_columns:
            if col in df.columns:
                try:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                    df[col] = df[col].dt.strftime("%Y-%m-%d")
                except Exception as e:
                    print(f"  [WARN] 日期列 {col} 格式化失败: {e}")

        if "业务类型" in df.columns:
            business_type_map = {
                "NORMAL": "普通应付单",
                "DEFECT": "退货应付单",
                "CONSIGNMENT": "受托代销应付单",
                "COMMISSION": "委托代销应付单",
                "OTHERRECE": "其他应收单",
                "OTHERPAY": "其他应付单",
                "INITIALRECE": "期初应收单",
                "INITIALPAY": "期初应付单",
                "CG": "采购",
                "FY": "费用",
                "采购": "采购",
                "费用": "费用",
            }
            df["业务类型"] = df["业务类型"].map(lambda x: business_type_map.get(str(x), str(x)))

        if "往来单位类型" in df.columns:
            contact_type_map = {
                "BD_Customer": "客户",
                "BD_Supplier": "供应商",
                "HSWD01_SYS": "供应商",
                "ORG_Organizations": "组织机构",
                "BD_OtherOrg": "其他组织",
                "BD_Employee": "员工",
                "BD_Empinfo": "员工",
                "BD_BANK": "银行",
            }
            df["往来单位类型"] = df["往来单位类型"].map(lambda x: contact_type_map.get(str(x), str(x)))

        status_map = {
            "Z": "暂存",
            "A": "创建",
            "B": "审核中",
            "C": "已审核",
            "D": "重新审核",
        }
        close_status_map = {
            "A": "未关闭",
            "B": "已关闭",
        }
        giveaway_map = {
            "true": "是",
            "false": "否",
        }

        if "单据状态" in df.columns:
            df["单据状态"] = df["单据状态"].map(lambda x: status_map.get(str(x), str(x)))
        if "关闭状态" in df.columns:
            df["关闭状态"] = df["关闭状态"].map(lambda x: close_status_map.get(str(x), str(x)))
        for col in ["是否赠品", "申请借款", "实报实付"]:
            if col in df.columns:
                df[col] = df[col].map(lambda x: giveaway_map.get(str(x).lower(), str(x)))

        if form_id == "IV_ReceivedInvoice":
            df = self._postprocess_received_invoice(df)

        return df[[col for col in columns if col in df.columns]]

    def _postprocess_received_invoice(self, df):
        if df is None or df.empty:
            return df

        df = df.copy()
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].map(lambda x: "" if pd.isna(x) else str(x).strip())

        header_columns = ["发票代码", "发票号码", "购货方名称", "销售方名称", "开票日期", "发票状态"]
        header_columns = [col for col in header_columns if col in df.columns]
        if "单据编号" in df.columns and header_columns:
            df[header_columns] = df[header_columns].replace("", pd.NA)
            df[header_columns] = df.groupby("单据编号", dropna=False)[header_columns].transform(lambda s: s.ffill().bfill())
            df[header_columns] = df[header_columns].fillna("")
        if "发票号码" in df.columns and header_columns:
            invoice_blank_mask = df["发票号码"].astype(str).str.strip().eq("")
            filled_header = df[header_columns].replace("", pd.NA).ffill()
            for col in header_columns:
                df.loc[invoice_blank_mask, col] = filled_header.loc[invoice_blank_mask, col]
            df[header_columns] = df[header_columns].fillna("")
            same_invoice_columns = [col for col in header_columns if col != "发票号码"]
            invoice_no = df["发票号码"].replace("", pd.NA)
            if same_invoice_columns and invoice_no.notna().any():
                df[same_invoice_columns] = df[same_invoice_columns].replace("", pd.NA)
                df[same_invoice_columns] = (
                    df.assign(__invoice_no=invoice_no)
                    .groupby("__invoice_no", dropna=False)[same_invoice_columns]
                    .transform(lambda s: s.ffill().bfill())
                    .where(invoice_no.notna(), df[same_invoice_columns])
                )
                df[same_invoice_columns] = df[same_invoice_columns].fillna("")

        if "发票状态" in df.columns:
            invoice_status_map = {
                "0": "正常",
                "1": "失控",
                "2": "作废",
                "3": "红冲",
                "4": "异常",
            }
            df["发票状态"] = df["发票状态"].map(lambda x: invoice_status_map.get(str(x).strip(), str(x).strip()))

        if "关联单据类型" in df.columns:
            bill_type_map = self._bill_type_display_map()
            df["关联单据类型"] = df["关联单据类型"].map(lambda x: bill_type_map.get(str(x).strip(), str(x).strip()))

        return df

    def _bill_type_display_map(self):
        mapping = {}
        for config in getattr(self, "bill_configs", []) or []:
            form_id = str(config.get("form_id", "")).strip()
            name = str(config.get("bill_name", "")).strip()
            if form_id and name:
                mapping[form_id] = name
        for config in getattr(self, "report_configs", []) or []:
            form_id = str(config.get("form_id", "")).strip()
            name = str(config.get("report_name", "")).strip()
            if form_id and name:
                mapping[form_id] = name
        mapping.update(
            {
                "IV_PUREXPINV": "采购费用发票",
                "IV_ReceivedInvoice": "收票单",
            }
        )
        return mapping

    def save_all_to_excel(self, dataframes_dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.output_dir / f"云星空经营数据_{self.period_name}_{timestamp}.xlsx"

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with pd.ExcelWriter(filename, engine="openpyxl") as writer:
                for sheet_name, df in dataframes_dict.items():
                    write_header = not self._is_kds_output_sheet(sheet_name)
                    df.to_excel(writer, sheet_name=sheet_name, index=False, header=write_header)

                    try:
                        ws = writer.sheets[sheet_name]
                        self._apply_excel_number_formats(sheet_name, df, ws)
                    except Exception as e:
                        print(f"  ! sheet {sheet_name} 数值格式设置失败: {e}")

            print(f"  Excel文件已生成: {filename}")
            return str(filename)
        except Exception as e:
            print(f"  保存Excel失败: {e}")
            return None

    def _is_kds_output_sheet(self, sheet_name):
        return sheet_name in {"资产负债表", "利润表", "现金流量表"} or str(sheet_name).startswith("报表")

    def _apply_excel_number_formats(self, sheet_name, df, ws):
        try:
            from openpyxl.styles import numbers
        except Exception:
            return

        if df is None or df.empty:
            return

        if sheet_name == "资金头寸表":
            amount_cols = ["(原币)期初余额", "(原币)本期收入", "(原币)本期支出", "(原币)本期余额"]
            count_cols = ["收入笔数", "支出笔数"]
        elif sheet_name == "银行存款流水账":
            amount_cols = ["收入金额", "支出金额", "金额"]
            count_cols = []
        else:
            amount_cols = []
            count_cols = []

        if sheet_name == "科目余额表" and "科目编码" in df.columns:
            col_idx = list(df.columns).index("科目编码") + 1
            for row in range(2, 2 + len(df)):
                cell = ws.cell(row=row, column=col_idx)
                cell.value = "" if cell.value is None else str(cell.value)
                cell.number_format = "@"

        if self._is_kds_output_sheet(sheet_name):
            for row in range(5, ws.max_row + 1):
                for col in range(2, ws.max_column + 1):
                    cell = ws.cell(row=row, column=col)
                    if cell.value is None or str(cell.value).strip() == "":
                        continue
                    try:
                        cell.value = float(str(cell.value).replace(",", "").strip())
                        cell.number_format = "#,##0.00"
                    except Exception:
                        pass

        for col_idx, col_name in enumerate(df.columns, start=1):
            series = df[col_name]
            if pd.api.types.is_integer_dtype(series):
                fmt = numbers.FORMAT_NUMBER_COMMA_SEPARATED1
            elif pd.api.types.is_float_dtype(series):
                fmt = "#,##0.00"
            else:
                fmt = None

            if sheet_name in ("资金头寸表", "银行存款流水账"):
                if col_name in amount_cols:
                    fmt = "#,##0.00"
                if col_name in count_cols:
                    fmt = numbers.FORMAT_NUMBER_COMMA_SEPARATED1

            if not fmt:
                continue

            for row in range(2, 2 + len(df)):
                ws.cell(row=row, column=col_idx).number_format = fmt

    def _drop_rows_with_empty_contactunit_name(self, df, contactunit_name_col="往来单位名称"):
        if df is None or df.empty:
            return df
        if contactunit_name_col not in df.columns:
            return df
        series = df[contactunit_name_col]
        return df[series.notna() & (series.astype(str).str.strip() != "")]

    def export_all_bills(self):
        print("=" * 60)
        print(f"销售单据数据导出 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        try:
            if not self.login_kingdee():
                return False

            self._resolve_org_scope_after_login()

            all_dataframes = {}
            bill_records = []

            for config in self.bill_configs:
                form_id = config["form_id"]
                bill_name = config["bill_name"]
                if self.only and (form_id.lower() not in self.only) and (bill_name.lower() not in self.only):
                    continue
                field_keys = self._append_extra_field_keys(config, config["field_keys"])
                filter_string = config["filter_string"]
                columns = config["columns"]

                print(f"\n处理单据: {bill_name}")
                print("-" * 60)

                data = self.get_bill_data_with_filter(form_id, field_keys, filter_string)
                df = self.parse_data_to_dataframe(data, columns, form_id=form_id)

                record_count = len(df)
                bill_records.append({"name": bill_name, "count": record_count})
                all_dataframes[bill_name] = df

                if record_count == 0:
                    print(f"  [WARN] {bill_name} 无数据（将创建空表）")
                else:
                    print(f"  {bill_name} 获取到 {record_count} 条记录")

            for config in self.report_configs:
                form_id = config["form_id"]
                report_name = config["report_name"]
                if self.only and (form_id.lower() not in self.only) and (report_name.lower() not in self.only):
                    continue
                field_keys = self._append_extra_field_keys(config, config.get("field_keys", ""))
                model = copy.deepcopy(config["model"])
                columns = config["columns"]

                if form_id in ("AP_SumReport", "AR_SumReport"):
                    settle_org_lst = self.resolve_settle_org_ids_by_numbers(self.target_settle_org_numbers, self.default_settle_org_id_map)
                    if form_id == "AP_SumReport":
                        model = self.build_ap_sum_report_model(settle_org_lst)
                    else:
                        model = self.build_ar_sum_report_model(settle_org_lst)
                elif config.get("org_id_model_field"):
                    settle_org_lst = self.resolve_settle_org_ids_by_numbers(self.target_settle_org_numbers, self.default_settle_org_id_map)
                    model[config["org_id_model_field"]] = settle_org_lst
                elif config.get("api_type") == "kds_report":
                    model["OrgNumber"] = self.inventory_org_number or (self.target_settle_org_numbers[0] if self.target_settle_org_numbers else "")

                print(f"\n处理报表: {report_name}")
                print("-" * 60)

                if config.get("api_type") == "kds_report":
                    data = self.get_kds_report_data(model)
                else:
                    data = self.get_report_data(form_id, field_keys, model, scheme_id=config.get("scheme_id", ""))
                df = self.parse_report_to_dataframe(data, columns, form_id=form_id)

                if isinstance(df, dict):
                    total_count = 0
                    for sheet_name, sheet_df in df.items():
                        record_count = len(sheet_df)
                        total_count += record_count
                        bill_records.append({"name": sheet_name, "count": record_count})
                        all_dataframes[sheet_name] = sheet_df
                        if record_count == 0:
                            print(f"  [WARN] {sheet_name} 无数据（将创建空表）")
                        else:
                            print(f"  {sheet_name} 获取到 {record_count} 条记录")
                    continue

                if form_id in ("AR_SumReport", "AP_SumReport"):
                    df = self._drop_rows_with_empty_contactunit_name(df, contactunit_name_col="往来单位名称")

                if report_name == "资金头寸表":
                    df = self.build_fund_position_output(df)

                record_count = len(df)
                bill_records.append({"name": report_name, "count": record_count})
                all_dataframes[report_name] = df

                if record_count == 0:
                    print(f"  [WARN] {report_name} 无数据（将创建空表）")
                else:
                    print(f"  {report_name} 获取到 {record_count} 条记录")

            print("\n正在生成Excel文件...")
            excel_file = self.save_all_to_excel(all_dataframes)

            if not excel_file:
                print("  Excel生成失败")
                return False

            print("\n生成的文件:")
            if os.path.exists(excel_file):
                print(f"  - {os.path.abspath(excel_file)}")

            print("=" * 60)
            print("导出任务完成")
            print("=" * 60)

            return True

        except Exception as e:
            print(f"导出任务异常：{e}")
            hint = error_hint_for(str(e))
            if hint:
                print(f"  → {hint}")
            if os.getenv("KINGDEE_DEBUG"):
                import traceback

                traceback.print_exc()
            print("  （需要完整堆栈时设置环境变量 KINGDEE_DEBUG=1 后重跑）")
            return False


def _version_sort_key(version):
    text = str(version or "").strip().lstrip("vV")
    parts = re.split(r"[^0-9A-Za-z]+", text)
    key = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return key


def is_newer_version(latest_version, current_version):
    return _version_sort_key(latest_version) > _version_sort_key(current_version)


def check_for_update(timeout=3):
    """检查 GitHub 最新 Release。失败时静默返回 None，不影响导出。"""
    try:
        response = requests.get(
            RELEASES_API_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"KingdeeDataExporter/{APP_VERSION}"},
            timeout=timeout,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        latest_version = str(data.get("tag_name") or "").strip()
        if not latest_version:
            return None
        release_url = data.get("html_url") or RELEASES_PAGE_URL
        if is_newer_version(latest_version, APP_VERSION):
            return {
                "current_version": APP_VERSION,
                "latest_version": latest_version,
                "url": release_url,
            }
    except Exception:
        return None
    return None


def print_update_notice(update_info):
    if not update_info:
        return
    print("=" * 60)
    print("发现 KingdeeDataExporter 新版本")
    print(f"当前版本: {update_info['current_version']}")
    print(f"最新版本: {update_info['latest_version']}")
    print(f"更新地址: {update_info['url']}")
    print("=" * 60)


def _query_all_pages(session, base_url, form_id, field_keys, filter_string="", page_size=2000, timeout=60):
    """按主键分页拉全量数据（不限内置清单，任意 FormId）。"""
    url = _normalize_base_url(base_url) + (
        "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
    )
    all_rows = []
    start = 0
    while True:
        payload = {
            "formid": form_id,
            "data": json.dumps({
                "FormId": form_id,
                "FieldKeys": field_keys,
                "FilterString": filter_string,
                "OrderString": "",
                "TopRowCount": 0,
                "StartRow": start,
                "Limit": page_size,
            }, ensure_ascii=False),
        }
        resp = session.post(url, json=payload, timeout=timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}：{(resp.text or '')[:200]}")
        rows = resp.json()
        if not isinstance(rows, list):
            raise RuntimeError(f"返回结构异常：{json.dumps(rows, ensure_ascii=False)[:200]}")
        for row in rows:
            if isinstance(row, dict) or (isinstance(row, list) and any(isinstance(x, dict) for x in row)):
                text = json.dumps(row, ensure_ascii=False)[:300]
                raise RuntimeError(f"接口返回错误对象：{text}\n      {error_hint_for(text)}")
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        start += page_size
    return all_rows


def export_generic_form(form_id, fields="", filter_string="", output_dir="."):
    """通用取数：把**任意**业务对象导出为 Excel，不限于内置清单。

    供下游分析类 skill（资金助手 / 账套体检 / 风险雷达）复用，
    避免每开发一个视角就回头改底座代码。

    用法：
      --form-id GL_Voucher                          # 自动取该对象全部字段
      --form-id GL_Voucher --fields FBillNo,FDate   # 指定字段
      --form-id GL_Voucher --filter "FDate>='2026-01-01'"
    """
    missing = get_missing_config_keys(KINGDEE_CONFIG)
    if missing:
        print_config_guide("配置不完整：" + "、".join(missing))
        return 3

    base_url = _normalize_base_url(KINGDEE_CONFIG.get("base_url"))
    session = _make_session()
    acctid = str(KINGDEE_CONFIG.get("acctid") or "").strip()
    if not acctid:
        acctid, note = resolve_acctid_by_name(base_url, KINGDEE_CONFIG.get("acct_name"))
        if not acctid:
            print(f"无法确定账套：{note}")
            return 3
    ok, info = perform_login(
        session, base_url, acctid, KINGDEE_CONFIG.get("username"), KINGDEE_CONFIG.get("password")
    )
    if not ok:
        print(f"登录失败：{info.get('message')}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        return 3

    keys = [k.strip() for k in str(fields or "").split(",") if k.strip()]
    sheet = form_id
    if not keys:
        print(f"未指定字段，正在读取 {form_id} 的完整字段清单…")
        try:
            meta = fetch_business_info(session, base_url, form_id)
        except Exception as exc:
            print(f"读取元数据失败：{exc}")
            return 3
        for entry in meta.get("Entrys") or []:
            if not isinstance(entry, dict):
                continue
            for field in entry.get("Fields") or []:
                key = str(field.get("Key") or "").strip()
                if key and key not in keys:
                    keys.append(key)
        sheet = _meta_name(meta.get("Name")) or form_id
        if not keys:
            print("该对象没有可用字段，请用 --fields 显式指定。")
            return 3

    print(f"对象：{form_id}（{sheet}）")
    print(f"字段：{len(keys)} 个")
    if filter_string:
        print(f"过滤：{filter_string}")

    try:
        rows = _query_all_pages(session, base_url, form_id, ",".join(keys), filter_string)
    except Exception as exc:
        print(f"取数失败：{exc}")
        return 3

    df = pd.DataFrame(rows, columns=keys)
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", str(sheet))[:60]
    path = out_dir / f"{safe_name}_{form_id}_{ts}.xlsx"
    try:
        with pd.ExcelWriter(path) as writer:
            df.to_excel(writer, sheet_name="数据", index=False)
    except Exception as exc:
        print(f"写入 Excel 失败：{exc}")
        return 3

    print(f"\n共 {len(df)} 行")
    print(f"已导出：{path}")
    return 0


def inspect_fields_command(form_id, keyword="", json_out=""):
    """`--inspect-fields` 的实现：登录 → QueryBusinessInfo → 打印字段清单。"""
    missing = get_missing_config_keys(KINGDEE_CONFIG)
    if missing:
        print_config_guide("配置不完整：" + "、".join(missing))
        return 3
    base_url = _normalize_base_url(KINGDEE_CONFIG.get("base_url"))
    session = _make_session()
    acctid = str(KINGDEE_CONFIG.get("acctid") or "").strip()
    if not acctid:
        acctid, note = resolve_acctid_by_name(base_url, KINGDEE_CONFIG.get("acct_name"))
        if not acctid:
            print(f"无法确定账套：{note}")
            return 3
    ok, info = perform_login(
        session, base_url, acctid, KINGDEE_CONFIG.get("username"), KINGDEE_CONFIG.get("password")
    )
    if not ok:
        print(f"登录失败：{info.get('message')}")
        if info.get("hint"):
            print(f"  → {info['hint']}")
        return 3
    try:
        meta = fetch_business_info(session, base_url, form_id)
    except Exception as exc:
        print(f"查询失败：{exc}")
        return 3
    print_business_info(meta, keyword, json_out)
    return 0


def main():
    parser = argparse.ArgumentParser(description="金蝶云星空经营数据导出工具")
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--org", help="组织编码；多个编码用英文逗号分隔，all 表示全部组织")
    parser.add_argument("--only", help="只导出指定 form_id 或中文名称；多个项目用英文逗号分隔")
    parser.add_argument("--fields", dest="extra_fields", help="追加字段，格式为 表单:字段；多个配置用英文逗号分隔。配合 --form-id 时改为逗号分隔的字段列表")
    parser.add_argument("--output-dir", default=".", help="导出文件保存目录，默认为当前目录")
    parser.add_argument("--list-orgs", action="store_true", help="导出组织列表后退出（组织 = 账套内的核算组织）")
    parser.add_argument("--show-config", action="store_true", help="显示可导出的单据和报表后退出")
    parser.add_argument("--check-update", action="store_true", help="检查是否有新版本（仅此选项会访问 GitHub），不执行导出")
    parser.add_argument(
        "--doctor", action="store_true",
        help="连接自检：配置 → 连通 → 账套 → 登录 → 取数冒烟，逐步给出修复建议",
    )
    parser.add_argument(
        "--list-datacenters", action="store_true",
        help="列出服务器上的全部账套（acctid 来源），无需账号密码",
    )
    parser.add_argument(
        "--inspect-fields", metavar="FORM_ID",
        help="列出某业务对象的实体与字段全清单（核对字段、排障用），如 --inspect-fields ER_ExpReimbursement",
    )
    parser.add_argument("--filter", dest="filter_keyword", default="", help="配合 --inspect-fields，按关键字过滤字段")
    parser.add_argument("--json-out", default="", help="配合 --inspect-fields，把完整元数据保存为 JSON 文件")
    parser.add_argument(
        "--form-id", dest="form_id", default="",
        help="通用取数：导出任意业务对象（不限于内置清单），如 GL_Voucher / FA_Card / STK_Inventory",
    )
    parser.add_argument(
        "--filter-string", dest="filter_string", default="",
        help="配合 --form-id，直接传金蝶 FilterString，如 \"FDate>='2026-01-01'\"",
    )
    parser.add_argument("--help-config", action="store_true", help="打印配置方法后退出")
    args = parser.parse_args()

    if args.help_config:
        print_config_guide()
        return

    if args.doctor:
        sys.exit(run_doctor())

    if args.list_datacenters:
        sys.exit(print_datacenters(KINGDEE_CONFIG.get("base_url")))

    if args.inspect_fields:
        sys.exit(inspect_fields_command(args.inspect_fields, args.filter_keyword, args.json_out))

    if args.form_id:
        sys.exit(export_generic_form(
            args.form_id, args.extra_fields or "", args.filter_string or "", args.output_dir
        ))

    if args.check_update:
        update_info = check_for_update()
        if update_info:
            print_update_notice(update_info)
        else:
            print(f"未发现新版本（当前版本: {APP_VERSION}；网络不可用时也会得到此结果）")
        return

    exporter = SalesDataExporter(
        start_date=args.start,
        end_date=args.end,
        org_numbers=args.org,
        only=args.only,
        extra_fields=args.extra_fields,
        output_dir=args.output_dir,
    )

    if args.show_config:
        print("可用导出项（--only 可填 form_id 或名称，支持逗号分隔）：")
        print("-" * 60)
        for c in exporter.bill_configs:
            print(f"[BILL] {c['form_id']}  |  {c['bill_name']}")
        for c in exporter.report_configs:
            print(f"[RPT ] {c['form_id']}  |  {c['report_name']}")
        return

    if args.list_orgs:
        orgs = exporter.get_all_organizations()
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            exporter.output_dir.mkdir(parents=True, exist_ok=True)
            filename = exporter.output_dir / f"组织列表_{ts}.xlsx"
            pd.DataFrame(orgs).to_excel(filename, index=False)
            print(f"组织列表已导出：{filename}")
        except Exception as e:
            print(f"组织列表导出失败（将改为打印到控制台）：{e}")
            for o in orgs:
                print(f"{o.get('number')}\t{o.get('name')}")
        return

    success = exporter.export_all_bills()
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
