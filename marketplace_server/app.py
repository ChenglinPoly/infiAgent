import io
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

# NOTE:
# This file is intentionally compatible with Python 3.6+ (CentOS 7 default).
# Do NOT use FastAPI/Pydantic here, as modern versions require Python >= 3.8/3.9.
# We provide a tiny WSGI app + a built-in server entrypoint.


ROOT = Path(__file__).resolve().parent
DEFAULT_SKILLS_DIR = (ROOT.parent / "skills").resolve()
DEFAULT_AGENT_LIB_DIR = (ROOT.parent / "config" / "agent_library").resolve()


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return Path(raw).expanduser().resolve()


SKILLS_DIR = _env_path("MARKET_SKILLS_DIR", DEFAULT_SKILLS_DIR)
AGENT_LIB_DIR = _env_path("MARKET_AGENT_LIBRARY_DIR", DEFAULT_AGENT_LIB_DIR)
STATE_PATH = ROOT / "state.json"


def _mk_item(kind: str, name: str, description: str, updated_at: float, downloads: int) -> Dict[str, Any]:
    return {
        "kind": kind,
        "name": name,
        "description": description or "",
        "updated_at": float(updated_at),
        "downloads": int(downloads),
    }


def _load_state() -> Dict[str, Any]:
    try:
        if not STATE_PATH.exists():
            return {"downloads": {"skills": {}, "agent_systems": {}}}
        return json.loads(STATE_PATH.read_text("utf-8"))
    except Exception:
        return {"downloads": {"skills": {}, "agent_systems": {}}}


def _save_state(state: Dict[str, Any]) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", "utf-8")
    tmp.replace(STATE_PATH)


def _inc_download(kind: str, name: str) -> int:
    state = _load_state()
    d = state.setdefault("downloads", {}).setdefault("skills" if kind == "skill" else "agent_systems", {})
    d[name] = int(d.get(name, 0)) + 1
    _save_state(state)
    return int(d[name])


def _get_downloads(kind: str, name: str) -> int:
    state = _load_state()
    d = state.get("downloads", {}).get("skills" if kind == "skill" else "agent_systems", {})
    return int(d.get(name, 0))


def _safe_frontmatter_description(skill_md: Path) -> str:
    # Very small parser: look for YAML-like frontmatter block and "description:" line.
    try:
        text = skill_md.read_text("utf-8", errors="ignore")
    except Exception:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end == -1:
        return ""
    fm = text[3:end]
    for line in fm.splitlines():
        if line.strip().startswith("description:"):
            return line.split("description:", 1)[1].strip().strip('"').strip("'")
    return ""


def _list_skills() -> List[Dict[str, Any]]:
    items = []  # type: List[Dict[str, Any]]
    if not SKILLS_DIR.exists():
        return items
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        desc = _safe_frontmatter_description(d / "SKILL.md")
        try:
            updated = max((p.stat().st_mtime for p in d.rglob("*") if p.exists()), default=d.stat().st_mtime)
        except Exception:
            updated = time.time()
        items.append(_mk_item("skill", d.name, desc or "", float(updated), _get_downloads("skill", d.name)))
    return items


def _list_agent_systems() -> List[Dict[str, Any]]:
    items = []  # type: List[Dict[str, Any]]
    if not AGENT_LIB_DIR.exists():
        return items
    for d in sorted(AGENT_LIB_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        # Best-effort description:
        # 1) extract alpha_agent.description from level_3_agents.yaml (more meaningful)
        # 2) fallback to first comment line of general_prompts.yaml
        desc = ""
        l3 = d / "level_3_agents.yaml"
        if l3.exists():
            try:
                text = l3.read_text("utf-8", errors="ignore").splitlines()
                in_alpha = False
                for line in text:
                    if not in_alpha and line.startswith("  alpha_agent:"):
                        in_alpha = True
                        continue
                    if in_alpha:
                        # next tool block
                        if line.startswith("  ") and not line.startswith("    "):
                            break
                        if "description:" in line:
                            # naive parse: description: "..."
                            parts = line.split("description:", 1)
                            if len(parts) == 2:
                                desc = parts[1].strip().strip('"').strip("'")
                                if desc:
                                    break
            except Exception:
                desc = ""
        if not desc:
            gp = d / "general_prompts.yaml"
            if gp.exists():
                try:
                    for raw in gp.read_text("utf-8", errors="ignore").splitlines():
                        t = raw.strip()
                        if t.startswith("#"):
                            desc = t.lstrip("#").strip()
                            if desc:
                                break
                except Exception:
                    desc = ""
        try:
            updated = max((p.stat().st_mtime for p in d.rglob("*") if p.exists()), default=d.stat().st_mtime)
        except Exception:
            updated = time.time()
        items.append(_mk_item("agent_system", d.name, desc or "", float(updated), _get_downloads("agent_system", d.name)))
    return items


def _apply_query(items: List[Dict[str, Any]], q: str) -> List[Dict[str, Any]]:
    query = (q or "").strip().lower()
    if not query:
        return items
    out = []
    for it in items:
        name = str(it.get("name") or "").lower()
        desc = str(it.get("description") or "").lower()
        if query in name or query in desc:
            out.append(it)
    return out


def _sort_items(items: List[Dict[str, Any]], sort_by: str, order: str) -> List[Dict[str, Any]]:
    key = (sort_by or "updated_at").strip()
    reverse = (order or "desc").strip().lower() != "asc"
    if key == "downloads":
        return sorted(items, key=lambda x: int(x.get("downloads", 0)), reverse=reverse)
    return sorted(items, key=lambda x: float(x.get("updated_at", 0.0)), reverse=reverse)


def _zip_dir_to_bytes(dir_path: Path, top_folder_name: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in dir_path.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(dir_path)
            arc = str(Path(top_folder_name) / rel)
            zf.write(p, arcname=arc)
    return buf.getvalue()


def _resolve_item_dir(kind: str, name: str) -> Path:
    base = SKILLS_DIR if kind == "skill" else AGENT_LIB_DIR
    p = (base / name).resolve()
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError("%s not found: %s" % (kind, name))
    # Prevent path traversal
    try:
        p.relative_to(base.resolve())
    except Exception:
        raise ValueError("Invalid name")
    return p


def _json_response(start_response, status: str, data: Dict[str, Any]) -> List[bytes]:
    body = (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
    ]
    start_response(status, headers)
    return [body]


def _bytes_response(start_response, status: str, content_type: str, body: bytes, extra_headers: Optional[List[Tuple[str, str]]] = None) -> List[bytes]:
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    start_response(status, headers)
    return [body]


def _not_found(start_response, msg: str) -> List[bytes]:
    return _json_response(start_response, "404 Not Found", {"ok": False, "error": msg})


def _bad_request(start_response, msg: str) -> List[bytes]:
    return _json_response(start_response, "400 Bad Request", {"ok": False, "error": msg})


def app(environ, start_response):
    """
    WSGI callable.
    Endpoints:
      - GET /api/v1/health
      - GET /api/v1/index?q=&sort=updated_at|downloads&order=asc|desc
      - GET /api/v1/skills/<name>/download
      - GET /api/v1/agent-systems/<name>/download
    """
    method = environ.get("REQUEST_METHOD", "GET").upper()
    if method != "GET":
        return _json_response(start_response, "405 Method Not Allowed", {"ok": False, "error": "Only GET is supported"})

    path = environ.get("PATH_INFO", "") or ""
    qs = parse_qs(environ.get("QUERY_STRING", "") or "")
    q = (qs.get("q", [""])[0] or "")
    sort = (qs.get("sort", ["updated_at"])[0] or "updated_at")
    order = (qs.get("order", ["desc"])[0] or "desc")

    if path == "/api/v1/health":
        return _json_response(
            start_response,
            "200 OK",
            {"ok": True, "skills_dir": str(SKILLS_DIR), "agent_library_dir": str(AGENT_LIB_DIR)},
        )

    if path == "/api/v1/index":
        skills = _sort_items(_apply_query(_list_skills(), q), sort, order)
        systems = _sort_items(_apply_query(_list_agent_systems(), q), sort, order)
        return _json_response(start_response, "200 OK", {"skills": skills, "agent_systems": systems})

    # Admin UI (upload)
    if path == "/admin":
        if not _check_admin(environ):
            return _json_response(start_response, "403 Forbidden", {"ok": False, "error": "admin token required"})
        # keep token in links if provided
        qs2 = parse_qs(environ.get("QUERY_STRING", "") or "")
        token_q = (qs2.get("token", [""])[0] or "").strip()
        token_hidden = '<input type="hidden" name="token" value="%s"/>' % _escape_html(token_q) if token_q else ""
        body = []
        body.append('<div class="box"><div class="muted">Skills dir: <code>%s</code><br/>Agent systems dir: <code>%s</code></div></div>' % (_escape_html(str(SKILLS_DIR)), _escape_html(str(AGENT_LIB_DIR))))
        if _admin_token_required() and not token_q:
            body.append('<div class="box"><b>提示</b>：已设置 <code>MARKET_ADMIN_TOKEN</code>，请用 <code>/admin?token=...</code> 打开管理页。</div>')
        body.append("""
<div class="box">
  <h3>Upload Skill (zip)</h3>
  <form method="POST" action="/api/v1/admin/upload-skill" enctype="multipart/form-data">
    %s
    <div class="row">
      <input type="file" name="file" accept=".zip" required/>
      <select name="strategy">
        <option value="overwrite">overwrite</option>
        <option value="keep_both">keep_both</option>
      </select>
      <button type="submit">Upload</button>
    </div>
  </form>
</div>
<div class="box">
  <h3>Upload Agent System (zip)</h3>
  <form method="POST" action="/api/v1/admin/upload-agent-system" enctype="multipart/form-data">
    %s
    <div class="row">
      <input type="file" name="file" accept=".zip" required/>
      <select name="strategy">
        <option value="overwrite">overwrite</option>
        <option value="keep_both">keep_both</option>
      </select>
      <button type="submit">Upload</button>
    </div>
  </form>
</div>
""" % (token_hidden, token_hidden))

        # Lists
        skills = _list_skills()
        systems = _list_agent_systems()
        body.append('<div class="box"><h3>Skills (%d)</h3>' % len(skills))
        body.append('<table><tr><th>Name</th><th>Description</th><th>Downloads</th><th>Updated</th></tr>')
        for it in _sort_items(skills, "updated_at", "desc"):
            body.append("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                _escape_html(it.get("name","")),
                _escape_html(it.get("description","")),
                _escape_html(str(it.get("downloads",""))),
                _escape_html(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(it.get("updated_at",0.0))))),
            ))
        body.append("</table></div>")
        body.append('<div class="box"><h3>Agent Systems (%d)</h3>' % len(systems))
        body.append('<table><tr><th>Name</th><th>Description</th><th>Downloads</th><th>Updated</th></tr>')
        for it in _sort_items(systems, "updated_at", "desc"):
            body.append("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                _escape_html(it.get("name","")),
                _escape_html(it.get("description","")),
                _escape_html(str(it.get("downloads",""))),
                _escape_html(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(it.get("updated_at",0.0))))),
            ))
        body.append("</table></div>")

        page = _html_page("infiAgent Marketplace Admin", "\n".join(body))
        return _bytes_response(start_response, "200 OK", "text/html; charset=utf-8", page)

    if path in ("/api/v1/admin/upload-skill", "/api/v1/admin/upload-agent-system"):
        if not _check_admin(environ):
            return _json_response(start_response, "403 Forbidden", {"ok": False, "error": "admin token required"})
        if method != "POST":
            return _json_response(start_response, "405 Method Not Allowed", {"ok": False, "error": "Only POST is supported"})
        try:
            import cgi
            fs = cgi.FieldStorage(fp=environ["wsgi.input"], environ=environ, keep_blank_values=True)
            f = fs["file"] if "file" in fs else None
            if not f or not getattr(f, "file", None):
                return _bad_request(start_response, "Missing file")
            strategy = (fs.getfirst("strategy", "overwrite") or "overwrite").strip()
            token_q = (fs.getfirst("token", "") or "").strip()
            # token in POST form also accepted
            if os.environ.get("MARKET_ADMIN_TOKEN", "").strip() and token_q:
                # emulate query token check
                if token_q != os.environ.get("MARKET_ADMIN_TOKEN", "").strip():
                    return _json_response(start_response, "403 Forbidden", {"ok": False, "error": "invalid token"})

            zip_bytes = f.file.read()
            kind = "skill" if path.endswith("upload-skill") else "agent_system"
            dest = SKILLS_DIR if kind == "skill" else AGENT_LIB_DIR
            dest.mkdir(parents=True, exist_ok=True)
            try:
                installed = _extract_zip_to_dest(zip_bytes, dest, strategy)
            except ValueError as e:
                if str(e) == "conflict":
                    return _json_response(start_response, "409 Conflict", {"ok": False, "error": "name conflict", "hint": "use keep_both or overwrite"})
                raise
            return _json_response(start_response, "200 OK", {"ok": True, "kind": kind, "installed_name": installed, "dest": str(dest)})
        except Exception as e:
            return _json_response(start_response, "500 Internal Server Error", {"ok": False, "error": str(e)})

    if path.startswith("/api/v1/skills/") and path.endswith("/download"):
        name = path[len("/api/v1/skills/") : -len("/download")].strip("/")
        if not name:
            return _bad_request(start_response, "Missing skill name")
        try:
            p = _resolve_item_dir("skill", name)
        except Exception as e:
            return _not_found(start_response, str(e))
        _inc_download("skill", name)
        data = _zip_dir_to_bytes(p, top_folder_name=name)
        return _bytes_response(
            start_response,
            "200 OK",
            "application/zip",
            data,
            extra_headers=[("Content-Disposition", 'attachment; filename="%s.zip"' % name)],
        )

    if path.startswith("/api/v1/agent-systems/") and path.endswith("/download"):
        name = path[len("/api/v1/agent-systems/") : -len("/download")].strip("/")
        if not name:
            return _bad_request(start_response, "Missing agent system name")
        try:
            p = _resolve_item_dir("agent_system", name)
        except Exception as e:
            return _not_found(start_response, str(e))
        _inc_download("agent_system", name)
        data = _zip_dir_to_bytes(p, top_folder_name=name)
        return _bytes_response(
            start_response,
            "200 OK",
            "application/zip",
            data,
            extra_headers=[("Content-Disposition", 'attachment; filename="%s.zip"' % name)],
        )

    return _not_found(start_response, "Unknown endpoint")


def _run_dev_server(host: str, port: int) -> None:
    from wsgiref.simple_server import make_server

    httpd = make_server(host, port, app)
    print("infiAgent Marketplace listening on http://%s:%s" % (host, port))
    httpd.serve_forever()


def _html_page(title: str, body_html: str) -> bytes:
    html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial,sans-serif; padding: 20px; max-width: 980px; margin: 0 auto; }}
    code, pre {{ font-family: ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; }}
    .box {{ border: 1px solid #ddd; border-radius: 10px; padding: 14px; margin: 12px 0; }}
    .row {{ display:flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
    input[type="text"] {{ padding: 8px 10px; border: 1px solid #ddd; border-radius: 8px; min-width: 320px; }}
    select, input[type="file"] {{ padding: 6px 8px; }}
    button {{ padding: 8px 12px; border: 1px solid #888; border-radius: 8px; background: #f6f6f6; cursor:pointer; }}
    button:hover {{ background: #efefef; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #eee; text-align: left; padding: 8px; vertical-align: top; }}
    .muted {{ color: #666; }}
  </style>
</head>
<body>
  <h2>{title}</h2>
  {body}
</body>
</html>
""".format(title=title, body=body_html)
    return html.encode("utf-8")


def _escape_html(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _admin_token_required() -> bool:
    return bool(os.environ.get("MARKET_ADMIN_TOKEN", "").strip())


def _check_admin(environ) -> bool:
    token = os.environ.get("MARKET_ADMIN_TOKEN", "").strip()
    if not token:
        return True
    # allow query ?token= or header X-Admin-Token
    qs = parse_qs(environ.get("QUERY_STRING", "") or "")
    qtok = (qs.get("token", [""])[0] or "").strip()
    htok = (environ.get("HTTP_X_ADMIN_TOKEN", "") or "").strip()
    return (qtok == token) or (htok == token)


def _extract_zip_to_dest(zip_bytes: bytes, dest_root: Path, strategy: str) -> str:
    import tempfile
    # Extract into temp dir first
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            zf.extractall(str(tmp))
        # Determine top folder
        entries = [p for p in tmp.iterdir() if p.name and not p.name.startswith(".")]
        dirs = [p for p in entries if p.is_dir()]
        if len(dirs) == 1:
            top = dirs[0]
        else:
            # if archive doesn't have a single top folder, treat tmp as top
            top = tmp
        base_name = top.name if top != tmp else "uploaded"
        install_name = base_name
        target = dest_root / install_name
        if target.exists():
            if strategy == "overwrite":
                # rm existing
                for p in sorted(target.rglob("*"), reverse=True):
                    try:
                        if p.is_file() or p.is_symlink():
                            p.unlink()
                        elif p.is_dir():
                            p.rmdir()
                    except Exception:
                        pass
                try:
                    target.rmdir()
                except Exception:
                    pass
            elif strategy == "keep_both":
                for i in range(2, 1000):
                    cand = dest_root / ("%s__%d" % (install_name, i))
                    if not cand.exists():
                        target = cand
                        install_name = cand.name
                        break
            else:
                raise ValueError("conflict")
        target.mkdir(parents=True, exist_ok=True)
        # Copy contents
        if top == tmp:
            src_root = tmp
        else:
            src_root = top
        for p in src_root.rglob("*"):
            rel = p.relative_to(src_root)
            out = target / rel
            if p.is_dir():
                out.mkdir(parents=True, exist_ok=True)
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(p.read_bytes())
    return install_name


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=18080, type=int)
    args = parser.parse_args()
    _run_dev_server(args.host, args.port)

