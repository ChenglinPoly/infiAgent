#!/usr/bin/env python3
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import load_panel
from tool_server_lite.tools.file_tools import BaseTool

class CheapClawReadPanelTool(BaseTool):
    name = "cheapclaw_read_panel"
    def execute(self, task_id, parameters):
        panel = load_panel()
        only_dirty = bool(parameters.get("only_dirty", False))
        channel = str(parameters.get("channel") or "").strip()
        conversation_id = str(parameters.get("conversation_id") or "").strip()
        channels = panel.get("channels", {})
        if channel:
            channels = {channel: channels.get(channel, {"conversations": {}})}
        if conversation_id:
            filtered = {}
            for ch, payload in channels.items():
                conv = payload.get("conversations", {}).get(conversation_id)
                if conv:
                    filtered[ch] = {"conversations": {conversation_id: conv}}
            channels = filtered
        if only_dirty:
            filtered = {}
            for ch, payload in channels.items():
                convs = {cid: conv for cid, conv in payload.get("conversations", {}).items() if conv.get("dirty")}
                if convs:
                    filtered[ch] = {"conversations": convs}
            channels = filtered
        return {"status": "success", "output": "ok", "panel": {"version": panel.get("version", 1), "channels": channels, "service_state": panel.get("service_state", {})}}
