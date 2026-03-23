# CheapClaw

CheapClaw is a social-message orchestration app built on top of the `infiagent/mla` SDK.

It started from a practical judgment about OpenClaw-style systems: the idea is good, but the operating cost is too high if you push everything through large models for long-running work. CheapClaw is aimed at the opposite direction. It tries to make weaker and cheaper models hold long tasks better by leaning on InfiAgent's runtime design instead of turning every message into a giant single-shot agent loop.

The core problem it solves is not "how to connect one more chat channel". The real problem is:

- a user sends a new request while several agents are already running
- sometimes the new message should continue an old task
- sometimes it should inject a new requirement into a running task
- sometimes it should start a parallel branch
- and the system needs to choose that path automatically without losing context

CheapClaw is built around that decision layer.

## Why CheapClaw exists

Compared with OpenClaw-like systems, the main motivation here is cost and long-horizon stability.

OpenClaw is impressive, but for many practical deployments it is expensive. CheapClaw uses `infiagent` as the execution substrate because `infiagent` already has several properties that matter for weaker models:

- short-step execution instead of giant long-context monologues
- resumable task memory keyed by `task_id`
- configurable fresh / resume behavior
- agent-system level composition
- SDK-level control over runtime, task state, and tool execution

That makes it much more suitable for small-model orchestration, especially when tasks are long and iterative.

## What is different

### 1. Instant message insertion into existing work

This is the main feature, not a side feature.

CheapClaw has a supervisor agent that decides how a new message should be routed:

- continue an old task by reusing the same `task_id`
- append a requirement to a currently running task without stopping it
- fork into a new task when the work is genuinely different

These are different operations and they are handled differently.

#### Continue an old task

If the work is still the same deliverable, CheapClaw can restart a new worker on the same `task_id`.

That matters because the old task keeps:

- workspace
- share context
- historical outputs
- prior task memory

So "modify the old report", "redo that script", "continue the previous result" does not have to become a brand new task.

#### Append to a running task

If a worker is still running, CheapClaw can inject a new requirement into that running task.

This does not require stopping the worker first. The requirement is appended and absorbed on the next safe loop boundary.

That is a different behavior from resuming an old task, and it is one of the main pain points CheapClaw is designed to solve.

### 2. Built on the InfiAgent SDK, not a closed custom runtime

CheapClaw is not a monolithic framework. It is an application built on the `infiagent` SDK.

That means it inherits several useful runtime capabilities:

- different thinking and execution models
- different models for different sub-agents
- mixed local models and provider models
- mixed API vendors in one overall system
- task-level runtime control through the SDK

In practice, this means you can build a system where:

- the supervisor uses one model
- the worker uses another
- a compression model is different again
- some parts use local inference and others use hosted APIs

This is configured at the agent-system level and in the model config.

### 3. Better behavior for weaker models

CheapClaw benefits from InfiAgent's short-step execution strategy.

For weak or small models, that matters a lot. With the same model, total cost can go either way depending on the exact task, but on long-running tasks the short-step strategy is often more stable and more cost-efficient than trying to force a weak model through a giant single planning loop.

Practical rule:

- the weaker the model, the shorter the step window should be
- do not set it below 10
- a good default is 20

### 4. Skills are not the only extension mechanism

CheapClaw supports normal skills, but it also treats full agent systems as a reusable extension layer.

In the default CheapClaw layout there are only two systems:

- `CheapClawSupervisor`
- `CheapClawWorkerGeneral`

But `infiagent` itself also ships with other agent systems, for example:

- `Researcher`
- `OpenCowork`

If you want to reuse them in this kind of setup, remove `human_in_loop` from their config first.

Using a full agent system as a reusable capability is sometimes better than a narrow skill:

- a skill is good for a compact workflow or tool pattern
- an agent system is good for a whole class of related tasks with a stronger internal role design

You can think of an agent system as a kind of "skill pro": broader coverage, more prompt budget, more specialization.

## Architecture

CheapClaw has three layers:

1. Channel adapters
2. A supervisor agent
3. Worker tasks running on InfiAgent

The supervisor does not do the real work. It decides:

- direct reply
- reuse old `task_id`
- append to running task
- start a new task
- restart / fresh / reset when needed

Workers do the execution.

## Current capabilities

- Telegram integration
- Feishu integration through long connection mode
- WhatsApp adapter scaffolding
- dashboard and panel view
- conversation-to-task binding
- task completion observation
- watchdog observation
- task-level visible skill filtering
- task-level message append
- task-level restart on the same `task_id`
- file sending for Telegram

## Skills behavior

CheapClaw uses task-level visible-skill filtering for worker agents.

By default, workers only see:

- `docx`
- `pptx`
- `xlsx`
- `find-skills`

The supervisor can expose more skills to a worker when needed.

This is implemented by filtering what the model sees in `<available_skills>`, not by breaking the global skill installation mechanism. That means normal skill installation still works.

## Install and run

The intended model is:

1. install `infiagent`
2. install CheapClaw's extra runtime dependencies
3. place CheapClaw in a separate repo
4. point it at a `user_data_root`
5. run it as an app

### 1. Install InfiAgent

Use the published package first:

```bash
python -m pip install -U infiagent==3.0.1
```

### 2. Install CheapClaw's extra dependencies

CheapClaw itself is an app layer on top of `infiagent`, so it still needs a few app-specific packages:

```bash
python -m pip install -U requests lark-oapi
```

If you only test Telegram first, `requests` is enough.  
If you want Feishu long-connection mode, install `lark-oapi` too.

### Bootstrap assets

```bash
python cheapclaw_service.py \
  --user-data-root /abs/path/to/user_root \
  --llm-config-path /abs/path/to/llm_config.yaml \
  --bootstrap
```

### Show runtime

```bash
python cheapclaw_service.py \
  --user-data-root /abs/path/to/user_root \
  --llm-config-path /abs/path/to/llm_config.yaml \
  --show-runtime
```

### Run one cycle

```bash
python cheapclaw_service.py \
  --user-data-root /abs/path/to/user_root \
  --llm-config-path /abs/path/to/llm_config.yaml \
  --run-once
```

### Run as a long-lived service

```bash
python cheapclaw_service.py \
  --user-data-root /abs/path/to/user_root \
  --llm-config-path /abs/path/to/llm_config.yaml \
  --run-loop
```

### Start the local dashboard

```bash
python cheapclaw_service.py \
  --user-data-root /abs/path/to/user_root \
  --llm-config-path /abs/path/to/llm_config.yaml \
  --serve-webhooks --host 127.0.0.1 --port 8765 \
  --run-loop
```

Then open:

- `http://127.0.0.1:8765/dashboard`

## Channel credentials

### Telegram

- `bot_token`

### Feishu

- `app_id`
- `app_secret`
- `verify_token`
- optional: `encrypt_key`

CheapClaw uses Feishu long connection mode, so it does not require a public webhook endpoint.

### WhatsApp Cloud API

- `access_token`
- `phone_number_id`
- `verify_token`

## Repository layout

- `cheapclaw_service.py`: main service entry
- `tool_runtime_helpers.py`: panel, task, and runtime helpers
- `assets/agent_library/`: supervisor and worker systems
- `assets/config/`: example config files
- `tools_library/`: CheapClaw-specific tools
- `skills/`: CheapClaw-specific skills
- `web/`: dashboard

## Notes for separate release

CheapClaw is intended to live in its own repository.

The framework-level changes that made it possible are mostly SDK and runtime improvements in `infiagent`, especially:

- SDK task control
- task snapshotting
- fresh / resume support
- tool hooks
- context hooks
- skill visibility filtering

If you publish `infiagent` to PyPI, CheapClaw can then be shipped as a clean separate application repo on top of that package.
