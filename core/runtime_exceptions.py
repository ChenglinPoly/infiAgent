#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行时异常定义。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class InfiAgentRunError(RuntimeError):
    """SDK / 库模式下用于向外部抛出的统一运行时异常。"""

    def __init__(
        self,
        message: str,
        *,
        task_id: str = "",
        agent_name: str = "",
        stage: str = "run",
        result: Optional[Dict[str, Any]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
        trace: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.task_id = str(task_id or "")
        self.agent_name = str(agent_name or "")
        self.stage = str(stage or "run")
        self.result = result or {}
        self.events = list(events or [])
        self.trace = trace

    @classmethod
    def from_result(
        cls,
        result: Optional[Dict[str, Any]],
        *,
        task_id: str = "",
        agent_name: str = "",
        stage: str = "run",
        events: Optional[List[Dict[str, Any]]] = None,
        trace: Optional[Dict[str, Any]] = None,
    ) -> "InfiAgentRunError":
        payload = result or {}
        message = (
            str(payload.get("error_information") or "").strip()
            or str(payload.get("error") or "").strip()
            or str(payload.get("output") or "").strip()
            or "InfiAgent run failed"
        )
        return cls(
            message,
            task_id=task_id,
            agent_name=agent_name,
            stage=stage,
            result=payload,
            events=events,
            trace=trace,
        )
