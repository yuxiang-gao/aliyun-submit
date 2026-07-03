# aliyun-submit

Agent skill for submitting and managing Alibaba Cloud PAI DLC training jobs. The skill bundles a self-contained [`scripts/dlc.py`](scripts/dlc.py) CLI and an [`example.yaml`](example.yaml) job config template.

Works with Cursor, Claude Code, Codex, and other agents that support the [Agent Skills](https://agentskills.io) format.

## Install

```bash
npx skills add yuxiang-gao/aliyun-submit -g -y
```

The `-g` flag installs the skill globally; omit it for a project-local install.

Browse skills at [skills.sh](https://skills.sh/).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) on your PATH
- A `.env` file with Aliyun credentials (see below)
- A job config YAML for your workspace (copy and edit `example.yaml`)

## Credentials

Create `.env` in your project root (or pass `--env_path` to the script):

```env
ALIBABA_CLOUD_ACCESS_KEY_ID=...
ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
ALIYUN_PAI_WORKSPACE_ID=...
ALIYUN_PAI_RESOURCE_ID=...
ALIYUN_REGION_ID=...
```

Never commit credentials. The script and skill instructions avoid printing secret values.

## Usage

From the installed skill directory (for example `~/.cursor/skills/aliyun-submit`):

```bash
# dry run — verify payload before submitting
uv run scripts/dlc.py submit \
  --config_path /path/to/your/job.yaml \
  --display_name my-job-smoke \
  --user_command 'sleep 100' \
  --dry_run true \
  --env_path /path/to/your/.env

# live submit
uv run scripts/dlc.py submit \
  --config_path /path/to/your/job.yaml \
  --display_name my-job-smoke \
  --user_command 'sleep 100' \
  --env_path /path/to/your/.env
```

Inspect or stop a job:

```bash
uv run scripts/dlc.py status dlc-job-id --env_path /path/to/your/.env
uv run scripts/dlc.py logs dlc-job-id --max_lines 200 --env_path /path/to/your/.env
uv run scripts/dlc.py events dlc-job-id --env_path /path/to/your/.env
uv run scripts/dlc.py metrics dlc-job-id --env_path /path/to/your/.env
uv run scripts/dlc.py stop dlc-job-id --env_path /path/to/your/.env
```

When your shell cwd is already the project that contains `.env`, you can omit `--env_path`.

## Job config

Copy `example.yaml` into your project and fill in workspace, resource quota, container image, data source mounts, and per-pod CPU/GPU/memory. CLI flags override YAML values.

Always dry-run before a live submit and confirm `DisplayName`, `WorkspaceId`, `ResourceId`, `UserCommand`, image, pod count, and resource limits in the printed payload.

## What the agent skill covers

After installation, agents load [`SKILL.md`](SKILL.md) when you ask about Aliyun DLC job submission. The skill focuses on:

- credential and config setup
- dry-run then live submit workflow
- inspecting logs, events, and metrics across pods
- stopping misconfigured jobs before retry

Project-specific training setup (syncing code to shared storage, composing `user_command` env blocks, etc.) stays in your own repo — the skill only handles DLC API submission.
