# -*- coding: utf-8 -*-
"""金蝶云星空连接凭据向导 —— **明文不落盘**，而且不要求用户装任何东西。

定位（改之前先读这段）
──────────────────────
本文件是**全系列金蝶连接凭据的唯一写入者**。`~/.workbuddy/kingdee/credentials.bin` 里只放
`base_url / acct_name / username / password / acctid`，**不放发票云**（发票云在
`piazzone.bin`，由报销助手自己管）。两个文件各有唯一写入者，谁也不会把谁的配置冲掉。

三条硬规矩
──────────
1. **不经过对话**：凭据只在本地窗口里输入，不进任何聊天记录。
2. **不落明文**：经 DPAPI 加密写入 `~/.workbuddy/kingdee/credentials.bin`，绑当前 Windows 用户。
3. **不回显、不写日志**：输入框掩码；只打印字段名是否存在，永不打印值。

用法
────
  python setup_credentials.py                # 配置窗口
  python setup_credentials.py --change-key   # 改密码（要求输两次）
  python setup_credentials.py --check        # 只看状态，不开窗
  python setup_credentials.py --delete       # 清除已保存凭据
  python setup_credentials.py --console      # 强制文字向导（排障用）

退出码（**agent 必须按码判断，不要看输出文字**）
──────────────────────────────────────────────
  0   已加密保存           10  用户取消/关窗/空闲超时（**没改成**，别盲目重跑）
  12  已有一个配置窗口开着   2   本机环境不支持       3   保存失败

界面降级顺序（零安装，绝不静默装任何东西）
──────────────────────────────────────────
  L0 本进程有 tkinter → 弹窗
  L1 本进程没有 → 找本机**已装的、带 tkinter 的另一个 Python**，由它弹窗（不改系统 PATH）
  L2 原生 Windows 表单（`win32_form.py`，纯 ctypes 调 user32）
  L3 独立控制台里的文字向导（密码走那个窗口自己的 stdin，不进 agent 管道）

⚠️ 已知坑
──────────
· `ttk.Entry` 不持有 `StringVar` 引用，循环里重新赋值会被 GC 清空输入框 —— 用 `VAR` 字典持住。
· 窗口过程/回调一旦被 GC，窗口创建即崩 —— 本文件不涉及，但 `win32_form` 里有这个坑。
"""

from __future__ import annotations

import argparse
import getpass
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import credstore  # noqa: E402

LEGACY_CONFIG = Path.home() / ".workbuddy" / "kingdee" / "config.json"

EXIT_OK = 0
EXIT_CANCELLED = 10
EXIT_BUSY = 12
EXIT_UNSUPPORTED = 2
EXIT_SAVE_FAILED = 3
EXIT_NEED_FALLBACK = 4

IDLE_TIMEOUT_MS = 20 * 60 * 1000
LOCK_PATH = credstore.STORE_DIR / ".setup.lock"

_EXPORTER_CANDIDATES = (
    Path(__file__).resolve().parent,
    Path(__file__).resolve().parent.parent,
    Path.home() / ".workbuddy" / "skills" / "kingdee-data-exporter",
    Path.home() / ".workbuddy" / "skills" / "KingdeeDataExporter",
)


class _NoUI(Exception):
    """图形界面建不起来（没有 tkinter、TclError、无桌面会话）。"""


# ─────────────────────────── 预填来源 ───────────────────────────

def _read_legacy_config() -> dict:
    if not LEGACY_CONFIG.is_file():
        return {}
    try:
        data = json.loads(LEGACY_CONFIG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    profiles = data.get("profiles")
    if isinstance(profiles, dict) and profiles:
        want = os.environ.get("KINGDEE_PROFILE") or str(data.get("default") or "")
        if not want:
            want = next(iter(profiles))
        picked = profiles.get(want)
        if isinstance(picked, dict):
            common = {k: v for k, v in data.items() if k not in ("profiles", "default")}
            merged = {**common, **picked}
            for old, new in (("server", "base_url"), ("acct", "acctid"),
                             ("user", "username"), ("pwd", "password")):
                if old in merged and new not in merged:
                    merged[new] = merged.pop(old)
            return merged
    return data


def _read_exporter_config() -> dict:
    for cand in _EXPORTER_CANDIDATES:
        if not (Path(cand) / "config.py").is_file():
            continue
        try:
            sys.path.insert(0, str(cand))
            from config import KINGDEE_CONFIG as KC  # type: ignore
            if isinstance(KC, dict):
                return {k: v for k, v in KC.items() if v}
        except Exception:  # noqa: BLE001
            continue
        finally:
            if str(cand) in sys.path:
                sys.path.remove(str(cand))
    return {}


def collect_prefill() -> dict:
    pre: dict = {}
    pre.update({k: v for k, v in _read_exporter_config().items()})
    pre.update({k: v for k, v in _read_legacy_config().items() if v})
    saved = credstore.load()
    if saved:
        pre.update({k: v for k, v in saved.items() if v and k != "piazzone"})
    return pre


def save_credentials(fields: dict) -> tuple[bool, str, list[str]]:
    """**合并写**：只覆盖本次这几个键。

    不能整份覆盖 —— 旧版本曾把发票云一起存在这个文件里，整份写会把别人写的段冲掉。
    现在发票云已迁走，但"合并写"这条要一直留着，防止以后再加字段时又踩一遍。
    """
    data = credstore.load() or {}
    data.update(fields)
    try:
        credstore.save(data)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), []
    notes = ["凭据已加密保存到：\n%s" % credstore.STORE_PATH]
    if LEGACY_CONFIG.is_file():
        try:
            LEGACY_CONFIG.unlink()
            notes.append("旧明文文件已删除：\n%s" % LEGACY_CONFIG)
        except OSError as exc:
            notes.append("⚠️ 明文文件删除失败，请手动删除：\n%s\n（%s）" % (LEGACY_CONFIG, exc))
    return True, "", notes


# ─────────────── 单实例锁（操作系统级，进程退出自动释放） ───────────────

_LOCK_FH = None


def _acquire_lock() -> bool:
    global _LOCK_FH
    try:
        credstore.STORE_DIR.mkdir(parents=True, exist_ok=True)
        fh = open(LOCK_PATH, "a+")
    except OSError:
        return True
    try:
        try:
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    try:
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
    except OSError:
        pass
    _LOCK_FH = fh
    return True


def _release_lock() -> None:
    global _LOCK_FH
    if _LOCK_FH is None:
        return
    try:
        _LOCK_FH.seek(0)
        try:
            import msvcrt
            msvcrt.locking(_LOCK_FH.fileno(), msvcrt.LK_UNLCK, 1)
        except ImportError:
            import fcntl
            fcntl.flock(_LOCK_FH.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        _LOCK_FH.close()
    except OSError:
        pass
    _LOCK_FH = None


# ─────────────── 找本机「带 tkinter 的 Python」（零安装） ───────────────

_PROBE_CODE = ("import sys, tkinter; "
               "sys.exit(0 if sys.version_info >= (3, 8) and tkinter.TkVersion else 1)")


def _has_tkinter() -> bool:
    try:
        import tkinter  # noqa: F401
        return bool(tkinter.TkVersion)
    except Exception:  # noqa: BLE001
        return False


def _probe(prefix: list[str]) -> bool:
    try:
        res = subprocess.run(prefix + ["-c", _PROBE_CODE], capture_output=True, timeout=10)
        return res.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _registry_pythons() -> list[str]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    out: list[str] = []
    roots = [(winreg.HKEY_CURRENT_USER, r"Software\Python\PythonCore"),
             (winreg.HKEY_LOCAL_MACHINE, r"Software\Python\PythonCore"),
             (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Python\PythonCore")]
    for hive, base in roots:
        try:
            with winreg.OpenKey(hive, base) as key:
                count = winreg.QueryInfoKey(key)[0]
                tags = [winreg.EnumKey(key, i) for i in range(count)]
        except OSError:
            continue
        for tag in tags:
            try:
                with winreg.OpenKey(hive, base + "\\" + tag + "\\InstallPath") as ik:
                    val, _ = winreg.QueryValueEx(ik, "")
            except OSError:
                continue
            path = str(val or "").strip()
            if not path:
                continue
            out.append(path if path.lower().endswith(".exe") else os.path.join(path, "python.exe"))
    return out


def _iter_python_candidates():
    seen: set[str] = set()
    me = os.path.normcase(os.path.abspath(sys.executable))

    def fresh(path: str) -> bool:
        if not path or not os.path.isfile(path):
            return False
        key = os.path.normcase(os.path.abspath(path))
        if key == me or key in seen:
            return False
        seen.add(key)
        return True

    launcher = shutil.which("py")
    if launcher:
        try:
            listed = subprocess.run([launcher, "-0p"], capture_output=True,
                                    text=True, timeout=10).stdout or ""
        except Exception:  # noqa: BLE001
            listed = ""
        for line in listed.splitlines():
            m = re.search(r"([A-Za-z]:\\[^\r\n]*?pythonw?\.exe)\s*$", line.strip())
            if m and fresh(m.group(1)):
                yield [m.group(1)]
        for tag in re.findall(r"-V:(\d+\.\d+)", listed):
            yield [launcher, "-" + tag]

    for path in _registry_pythons():
        if fresh(path):
            yield [path]

    for pat in (r"%LOCALAPPDATA%\Programs\Python\Python3*\python.exe",
                r"%PROGRAMFILES%\Python3*\python.exe",
                r"%PROGRAMFILES(X86)%\Python3*\python.exe",
                r"C:\Python3*\python.exe"):
        expanded = os.path.expandvars(pat)
        if "%" in expanded:
            continue
        for path in sorted(glob.glob(expanded), reverse=True):
            if fresh(path):
                yield [path]

    for name in ("python3", "python"):
        path = shutil.which(name)
        if path and fresh(path):
            yield [path]


def _find_tkinter_python(limit: int = 6) -> list[str] | None:
    tried = 0
    for prefix in _iter_python_candidates():
        tried += 1
        if tried > limit:
            break
        if _probe(prefix):
            return prefix
    return None


# ─────────────────────────────── 图形界面 ───────────────────────────────

def run_gui(change_key: bool = False) -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except Exception as exc:  # noqa: BLE001
        raise _NoUI("没有 tkinter（%s）" % exc) from exc

    if not _acquire_lock():
        print("已经有一个凭据配置窗口开着。请在那个窗口里填完，不要再开第二个。")
        return EXIT_BUSY
    try:
        return _run_gui_inner(change_key, tk, messagebox, ttk)
    finally:
        _release_lock()


def _run_gui_inner(change_key: bool, tk, messagebox, ttk) -> int:
    pre = collect_prefill()
    legacy_has_secret = bool(str(_read_legacy_config().get("password") or "").strip())
    saved_exists = credstore.exists()

    try:
        root = tk.Tk()
    except Exception as exc:  # noqa: BLE001
        raise _NoUI("窗口创建失败（%s）" % exc) from exc

    root.title("金蝶云星空 · 修改密钥" if change_key else "金蝶云星空 · 连接凭据")
    root.resizable(False, False)

    FS = "Microsoft YaHei UI"
    frm = ttk.Frame(root, padding=16)
    frm.grid(sticky="nsew")

    ttk.Label(frm, text="金蝶云星空 · 修改密钥" if change_key else "金蝶云星空 · 连接凭据",
              font=(FS, 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
    ttk.Label(frm, foreground="#666", justify="left", wraplength=470, text=(
        "这份凭据全系列共用（取数 / 分析 / 报销都读它），只需要在这里配一次。\n"
        "用 Windows 系统加密保存在本机：不写明文、不进对话记录。"
    )).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))

    VAR: dict[str, tk.StringVar] = {}

    def sv(key: str, value: str = "") -> tk.StringVar:
        VAR[key] = tk.StringVar(value=value)
        return VAR[key]

    rows = [
        ("base_url", "服务器地址", "例如 https://你的域名.ik3cloud.com"),
        ("acct_name", "公司名 / 账套", "不知道写哪个就先留空"),
        ("username", "用户名", ""),
    ]
    r = 2
    for key, label, hint in rows:
        ttk.Label(frm, text=label).grid(row=r, column=0, sticky="e", pady=4, padx=(0, 10))
        ttk.Entry(frm, textvariable=sv(key, str(pre.get(key) or "")), width=38
                  ).grid(row=r, column=1, sticky="we", pady=4)
        if hint:
            ttk.Label(frm, text=hint, foreground="#999").grid(row=r, column=2, sticky="w", padx=(8, 0))
        r += 1

    pwd_entry = ttk.Entry(frm, textvariable=sv("password", ""), width=38, show="*")
    ttk.Label(frm, text="新密码" if change_key else "密码"
              ).grid(row=r, column=0, sticky="e", pady=4, padx=(0, 10))
    pwd_entry.grid(row=r, column=1, sticky="we", pady=4)
    show_pwd = tk.BooleanVar(value=False)
    pwd2_entry = None

    def _toggle() -> None:
        ch = "" if show_pwd.get() else "*"
        pwd_entry.configure(show=ch)
        if pwd2_entry is not None:
            pwd2_entry.configure(show=ch)

    ttk.Checkbutton(frm, text="显示密码", variable=show_pwd, command=_toggle
                    ).grid(row=r, column=2, sticky="w", padx=(8, 0))
    r += 1
    if change_key:
        ttk.Label(frm, text="再输一次").grid(row=r, column=0, sticky="e", pady=4, padx=(0, 10))
        pwd2_entry = ttk.Entry(frm, textvariable=sv("password2", ""), width=38, show="*")
        pwd2_entry.grid(row=r, column=1, sticky="we", pady=4)
        r += 1

    if legacy_has_secret:
        box = ttk.LabelFrame(frm, text="检测到旧版明文配置", padding=10)
        box.grid(row=r, column=0, columnspan=3, sticky="we", pady=(12, 0))
        ttk.Label(box, foreground="#b00", wraplength=460, justify="left", text=(
            "本机存在明文文件：\n%s\n里面的密码是明文保存的。保存后会自动删除它；"
            "建议同时到金蝶后台改一次密码。" % LEGACY_CONFIG)
        ).grid(row=0, column=0, sticky="w")
        r += 1

    status = ttk.Label(frm, foreground="#666", justify="left", wraplength=470, text="")
    status.grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 0))
    status.configure(text="当前加密凭据：" + credstore.describe())

    RESULT = {"code": None}

    def on_save() -> None:
        base_url = VAR["base_url"].get().strip()
        acct_name = VAR["acct_name"].get().strip()
        username = VAR["username"].get().strip()
        password = VAR["password"].get()
        if not (username and password):
            messagebox.showwarning("还差一点", "用户名和密码是必填项。", parent=root)
            return
        if change_key and password != VAR["password2"].get():
            messagebox.showwarning("两次不一致", "两次输入的密码不一样，请核对后再保存。",
                                   parent=root)
            return
        if not (base_url or acct_name):
            messagebox.showwarning("还差一点", "请至少填「服务器地址」或「公司名 / 账套」之一。",
                                   parent=root)
            return
        fields = {"base_url": base_url, "acct_name": acct_name,
                  "username": username, "password": password}
        if str(pre.get("acctid") or "").strip():
            fields["acctid"] = str(pre["acctid"]).strip()

        ok, err, notes = save_credentials(fields)
        if not ok:
            messagebox.showerror("保存失败", err, parent=root)
            return
        if legacy_has_secret:
            notes.append("安全建议：旧密码曾以明文存在本机，请到金蝶后台改一次密码。")
        messagebox.showinfo("完成", "\n\n".join(notes), parent=root)
        RESULT["code"] = EXIT_OK
        root.destroy()

    def _snapshot() -> tuple:
        return tuple(v.get() for v in VAR.values())

    initial = _snapshot()

    def on_close() -> None:
        if RESULT["code"] == EXIT_OK:
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            if _snapshot() != initial:
                if not messagebox.askyesno("还没保存", "填写的内容还没保存，确定关闭吗？",
                                           default="no", parent=root):
                    return
        except Exception:  # noqa: BLE001
            pass
        RESULT["code"] = EXIT_CANCELLED
        try:
            root.destroy()
        except Exception:  # noqa: BLE001
            pass

    root.protocol("WM_DELETE_WINDOW", on_close)

    watchdog = {"id": None}

    def _arm() -> None:
        if watchdog["id"] is not None:
            try:
                root.after_cancel(watchdog["id"])
            except Exception:  # noqa: BLE001
                pass
        watchdog["id"] = root.after(IDLE_TIMEOUT_MS, _expire)

    def _expire() -> None:
        watchdog["id"] = None
        try:
            messagebox.showinfo("已自动关闭",
                                "窗口 20 分钟没有操作，已自动关闭（没有保存任何内容）。",
                                parent=root)
        except Exception:  # noqa: BLE001
            pass
        RESULT["code"] = EXIT_CANCELLED
        try:
            root.destroy()
        except Exception:  # noqa: BLE001
            pass

    root.bind_all("<Key>", lambda _e: _arm(), add="+")
    root.bind_all("<Button-1>", lambda _e: _arm(), add="+")
    _arm()

    btns = ttk.Frame(frm)
    btns.grid(row=r + 1, column=0, columnspan=3, sticky="e", pady=(14, 0))
    ttk.Button(btns, text="保存", command=on_save).grid(row=0, column=1, padx=(0, 8))
    ttk.Button(btns, text="取消", command=on_close).grid(row=0, column=2)

    if saved_exists:
        def on_clear() -> None:
            if messagebox.askyesno("确认", "删除本机已保存的加密凭据？", parent=root):
                credstore.delete()
                status.configure(text="当前加密凭据：" + credstore.describe())
        ttk.Button(btns, text="清除已保存凭据", command=on_clear).grid(row=0, column=0, padx=(0, 8))

    try:
        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        root.geometry("+%d+%d" % ((root.winfo_screenwidth() - w) // 2,
                                  max((root.winfo_screenheight() - h) // 3, 12)))
        root.attributes("-topmost", True)
        root.lift()
    except Exception:  # noqa: BLE001
        pass

    root.mainloop()
    return RESULT["code"] if RESULT["code"] is not None else EXIT_CANCELLED


# ────────────────────────── 原生表单（L2） ──────────────────────────

def _native_form(change_key: bool) -> int:
    try:
        import win32_form as wf
    except Exception as exc:  # noqa: BLE001
        print("原生表单不可用（%s）。" % exc)
        return EXIT_NEED_FALLBACK
    if not wf.available():
        return EXIT_NEED_FALLBACK

    if not _acquire_lock():
        print("已经有一个凭据配置窗口开着。请在那个窗口里填完，不要再开第二个。")
        return EXIT_BUSY
    try:
        pre = collect_prefill()
        legacy_has_secret = bool(str(_read_legacy_config().get("password") or "").strip())
        try:
            got = wf.run_form(change_key=change_key,
                              prefill={"base_url": pre.get("base_url") or "",
                                       "acct_name": pre.get("acct_name") or "",
                                       "username": pre.get("username") or ""},
                              show_piazzone=False)      # 发票云不归本技能
        except Exception as exc:  # noqa: BLE001
            print("原生表单创建失败（%s: %s）。" % (type(exc).__name__, exc))
            return EXIT_NEED_FALLBACK
        if got is None:
            print("用户取消了录入（没有保存任何内容）。")
            return EXIT_CANCELLED
        fields = {"base_url": got["base_url"], "acct_name": got["acct_name"],
                  "username": got["username"], "password": got["password"]}
        if str(pre.get("acctid") or "").strip():
            fields["acctid"] = str(pre["acctid"]).strip()
        ok, err, notes = save_credentials(fields)
        if not ok:
            wf.message("保存失败：\n%s" % err, "保存失败", warning=True)
            return EXIT_SAVE_FAILED
        if legacy_has_secret:
            notes.append("安全建议：旧密码曾以明文存在本机，请到金蝶后台改一次密码。")
        wf.message("\n\n".join(notes), "完成")
        return EXIT_OK
    finally:
        _release_lock()


# ────────────────────────── 文字向导（L3） ──────────────────────────

def _mask(pwd: str) -> str:
    n = len(pwd or "")
    return "（已填写 %d 个字符）" % n if n else "（空）"


def _pad(text: str, width: int) -> str:
    w = 0
    for ch in text:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 1
    return text + " " * max(width - w, 0)


def _console_wizard(change_key: bool = False) -> int:
    pre = collect_prefill()
    legacy_has_secret = bool(str(_read_legacy_config().get("password") or "").strip())

    steps = [
        ["base_url", "服务器地址", str(pre.get("base_url") or ""), False],
        ["acct_name", "公司名 / 账套", str(pre.get("acct_name") or ""), False],
        ["username", "用户名", str(pre.get("username") or ""), False],
        ["password", "新密码" if change_key else "密码", "", True],
    ]
    if change_key:
        steps.append(["password2", "再输一次（防打错）", "", True])

    print("=" * 64)
    print("金蝶云星空 · 连接凭据（文字向导）")
    print("输入的密码不会出现在对话里，也不会以明文存到磁盘。")
    print("关掉这个窗口 = 放弃；输 q 也可随时放弃。")
    print("=" * 64)

    values: dict = {}

    def ask(i: int):
        key, label, default, secret = steps[i]
        print("")
        if secret:
            print("  [%d/%d] %s" % (i + 1, len(steps), label))
            print("        输入时不显示任何字符（连星号也没有），输完按回车。")
        else:
            print("  [%d/%d] %s%s" % (i + 1, len(steps), label,
                                      "" if not default else "（直接回车沿用 %s）" % default))
            print("        （输 - 回上一项，输 q 放弃）")
        while True:
            try:
                val = getpass.getpass("  > ") if secret else input("  > ")
            except (EOFError, KeyboardInterrupt):
                return None
            if not secret:
                val = val.strip()
                if val.lower() == "q":
                    return None
                if val == "-":
                    if i > 0:
                        return {"__back__": True}
                    print("    已经是第一项了。")
                    continue
                if not val and default:
                    return default
            if val:
                return val
            print("    这一项必填，请重新输入。")

    i = 0
    while i < len(steps):
        got = ask(i)
        if got is None:
            print("\n已取消，没有保存任何内容。")
            return EXIT_CANCELLED
        if isinstance(got, dict) and got.get("__back__"):
            i = max(i - 1, 0)
            continue
        values[steps[i][0]] = got
        i += 1

    while True:
        print("")
        print("  即将保存（密码不显示内容，只显示长度）：")
        for n, (key, label, _d, _s) in enumerate(steps, start=1):
            shown = _mask(values.get(key, "")) if key in ("password", "password2") \
                else (values.get(key) or "（空）")
            print("    %d) %s: %s" % (n, _pad(label, 22), shown))
        try:
            ans = input("\n  回车 = 确认保存     数字 = 重填该项     q = 放弃： ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消，没有保存任何内容。")
            return EXIT_CANCELLED
        if ans.lower() == "q":
            print("已取消，没有保存任何内容。")
            return EXIT_CANCELLED
        if not ans:
            if change_key and values.get("password") != values.get("password2"):
                print("\n  ⚠️ 两次输入的密码不一样，还没有保存。")
                print("     请用序号重填「新密码」和「再输一次」，两遍一致才会保存。")
                continue
            break
        if ans.isdigit() and 1 <= int(ans) <= len(steps):
            j = int(ans) - 1
            got = ask(j)
            if got is None:
                print("\n已取消，没有保存任何内容。")
                return EXIT_CANCELLED
            if isinstance(got, dict) and got.get("__back__"):
                continue
            values[steps[j][0]] = got
            continue
        print("  （只认回车、序号或 q）")

    fields = {"base_url": values["base_url"], "acct_name": values["acct_name"],
              "username": values["username"], "password": values["password"]}
    if str(pre.get("acctid") or "").strip():
        fields["acctid"] = str(pre["acctid"]).strip()

    ok, err, notes = save_credentials(fields)
    if not ok:
        print("\n❌ 保存失败：%s" % err)
        return EXIT_SAVE_FAILED
    if legacy_has_secret:
        notes.append("安全建议：旧密码曾以明文存在本机，请到金蝶后台改一次密码。")
    print("")
    for line in notes:
        print("✓ " + line)
    try:
        input("\n按回车关闭这个窗口…")
    except (EOFError, KeyboardInterrupt):
        pass
    return EXIT_OK


# ─────────────────────────────── 启动器 ───────────────────────────────

def _try_ui(change_key: bool) -> int | None:
    try:
        return run_gui(change_key=change_key)
    except _NoUI as exc:
        print("图形界面打不开：%s" % exc)
        return None
    except Exception as exc:  # noqa: BLE001
        print("图形界面异常（%s: %s），改用其它方式。" % (type(exc).__name__, exc))
        return None


def _relaunch(prefix: list[str], flag: str, change_key: bool) -> int:
    script = str(Path(__file__).resolve())
    cmd = list(prefix) + [script, flag] + (["--change-key"] if change_key else [])
    flags = 0
    if flag == "--console-child":
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if os.name == "nt" else 0
    try:
        proc = subprocess.run(cmd, creationflags=flags, timeout=40 * 60)
    except subprocess.TimeoutExpired:
        print("录入窗口超过 40 分钟未完成，已放弃（没有保存任何内容）。")
        return EXIT_CANCELLED
    except OSError as exc:
        print("启动 %s 失败：%s" % (" ".join(cmd), exc))
        return EXIT_NEED_FALLBACK
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="金蝶云星空连接凭据向导（加密保存、不落明文）")
    ap.add_argument("--check", action="store_true", help="只打印状态，不开窗")
    ap.add_argument("--delete", action="store_true", help="删除已保存的加密凭据")
    ap.add_argument("--change-key", dest="change_key", action="store_true",
                    help="改密码（要求输两次）")
    ap.add_argument("--console", action="store_true", help="强制文字向导（排障用）")
    ap.add_argument("--native", action="store_true", help="强制原生表单（排障用）")
    ap.add_argument("--ui-child", dest="ui_child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--console-child", dest="console_child", action="store_true",
                    help=argparse.SUPPRESS)
    a = ap.parse_args()

    if a.delete:
        print("已删除" if credstore.delete() else "（没有已保存的加密凭据）")
        return EXIT_OK

    if a.check:
        print("平台         :", sys.platform)
        print("DPAPI 可用   :", credstore.available())
        print("加密凭据文件 :", credstore.STORE_PATH, "存在" if credstore.exists() else "不存在")
        print("加密凭据内容 :", credstore.describe())
        try:
            import win32_form as _wf
            native_ok = _wf.available()
        except Exception:  # noqa: BLE001
            native_ok = False
        print("录入界面     : tkinter=%s ｜ 原生表单=%s ｜ 文字向导=是"
              % ("有" if _has_tkinter() else "无（会自动另找解释器）",
                 "可用" if native_ok else "不可用"))
        has_plain = LEGACY_CONFIG.is_file() and str(_read_legacy_config().get("password") or "").strip()
        print("旧版明文配置 :", LEGACY_CONFIG, "存在（含明文密码）" if has_plain else "不存在")
        print("就绪状态     :", "❌ 未迁移完成 —— 取数命令会被闸门阻断" if has_plain
              else ("✅ 已用加密凭据" if credstore.exists() else "⚠️ 尚无凭据，需先配置"))
        return EXIT_OK

    if not credstore.available():
        print("本机不是 Windows（或缺少 DPAPI），无法加密保存凭据，因此不提供录入窗口。")
        print("可选：① 在 Windows 电脑上使用本技能（推荐）；")
        print("      ② 临时用环境变量 KINGDEE_* —— 注意环境变量在本机并不保密。")
        return EXIT_UNSUPPORTED

    if a.ui_child:
        code = _try_ui(a.change_key)
        return EXIT_NEED_FALLBACK if code is None else code
    if a.console_child or a.console:
        return _console_wizard(change_key=a.change_key)
    if a.native:
        return _native_form(a.change_key)

    if _has_tkinter():
        code = _try_ui(a.change_key)
        if code is not None:
            return code

    prefix = _find_tkinter_python()
    if prefix:
        print("当前解释器没有 tkinter，改用本机已装的 Python 打开录入窗口：%s" % " ".join(prefix))
        code = _relaunch(prefix, "--ui-child", a.change_key)
        if code != EXIT_NEED_FALLBACK:
            return code

    code = _native_form(a.change_key)
    if code != EXIT_NEED_FALLBACK:
        return code

    print("改用文字向导：马上会弹出一个黑色的录入窗口，")
    print("请在**那个窗口**里按提示填写（密码不会出现在这里）。")
    return _relaunch([sys.executable], "--console-child", a.change_key)


if __name__ == "__main__":
    raise SystemExit(main())
