---
name: cheapclaw-watchdog
description: Read CheapClaw watchdog observations and decide whether to inspect logs, fresh a task, ask for user input, or reset the task.
---

# CheapClaw Watchdog Skill

Use this skill when the trigger reason or panel events indicate watchdog observations, stalled tasks, repeated fresh attempts, or process health anomalies.

Checklist:
1. Read the CheapClaw panel and locate conversations/tasks with watchdog observations.
2. Inspect task status, latest thinking, final output, log path, and share context path.
3. If necessary, read the tail of the log file before deciding.
4. Distinguish between quiet-but-alive tasks and truly dead/stalled tasks.
5. Prefer reversible actions first: send status message, append clarification, or fresh.
6. Only reset a task when the evidence is strong and the loop cannot recover safely.
