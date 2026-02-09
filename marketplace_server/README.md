# Marketplace Server (FastAPI)

该服务提供一个非常轻量的 “Skills + Agent Systems 市场”：

- Skills 来源：仓库根目录 `skills_libraru/`
- Agent Systems 来源：仓库根目录 `config/agent_library/`
- 支持：列表、搜索、按下载量/更新时间排序、zip 下载

## 运行

```bash
python3 -m venv .venv && source .venv/bin/activate
# 默认无第三方依赖（兼容 CentOS7 的 Python 3.6+）
python3 marketplace_server/app.py --host 0.0.0.0 --port 18080
```

## 部署到服务器（推荐：systemd + nginx）

假设你把本仓库放到 `/opt/infiagent-market`（里面包含 `skills_libraru/` 与 `config/agent_library/`）：

```bash
cd /opt/infiagent-market
python3 -m venv .venv
source .venv/bin/activate
# 默认无第三方依赖（兼容 CentOS7 的 Python 3.6+）
```

- systemd：
  - 复制 `marketplace_server/infiagent-market.service` 到 `/etc/systemd/system/`
  - `systemctl daemon-reload && systemctl enable --now infiagent-market`
- nginx：
  - 复制 `marketplace_server/nginx_infiagent_market.conf` 到 `/etc/nginx/conf.d/`
  - `nginx -t && systemctl reload nginx`

然后在桌面端 Settings → Environment 填入市场地址，例如 `http://<你的服务器IP>`。

## API

- `GET /api/v1/health`
- `GET /api/v1/index`
- `GET /api/v1/skills/{name}/download`
- `GET /api/v1/agent-systems/{name}/download`
- `GET /admin`（上传管理界面）
- `POST /api/v1/admin/upload-skill`（zip 上传）
- `POST /api/v1/admin/upload-agent-system`（zip 上传）

## 配置

可选环境变量：

- `MARKET_SKILLS_DIR`: skills 目录（默认 `../skills_libraru`）
- `MARKET_AGENT_LIBRARY_DIR`: agent_library 目录（默认 `../config/agent_library`）
- `MARKET_ADMIN_TOKEN`: 可选的管理 token。设置后访问管理页需要 `/admin?token=...` 或请求头 `X-Admin-Token: ...`。

