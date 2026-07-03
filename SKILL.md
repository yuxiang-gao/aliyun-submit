---
name: aliyun-submit
description: Submit, inspect, and stop Alibaba Cloud PAI DLC training jobs via the Python SDK. Use when the user mentions Aliyun, Alibaba Cloud, 阿里云, PAI DLC, DLC, cloud GPU jobs, or training job submission.
---

# Aliyun DLC Job Submission

Submit and manage Alibaba Cloud PAI DLC jobs with the bundled `scripts/dlc.py` uv script. Paths below are relative to this skill directory unless noted.

## Prerequisites

1. Install [uv](https://docs.astral.sh/uv/).
2. Put credentials in a `.env` file in the working project (or pass `--env_path`):

   - `ALIBABA_CLOUD_ACCESS_KEY_ID`
   - `ALIBABA_CLOUD_ACCESS_KEY_SECRET`
   - `ALIYUN_PAI_WORKSPACE_ID`
   - `ALIYUN_PAI_RESOURCE_ID`
   - `ALIYUN_REGION_ID`

3. Create a job config YAML in the user's project. Start from `example.yaml` in this skill and fill in workspace, resource, image, data sources, and resource limits.

Never print `.env` values or Aliyun credentials. To verify setup, report only whether required keys are present.

## Script

`scripts/dlc.py` is a self-contained uv script. Run it with `uv`; callers do not need a separate project extra or virtualenv.

```bash
uv run scripts/dlc.py <verb> ...
```

Verbs: `submit`, `status`, `logs`, `events`, `metrics`, `stop`.

When running from the user's project instead of the skill directory, pass absolute paths for `--env_path` and `--config_path`, or `cd` into the skill directory first.

Before importing Aliyun SDK classes for direct probes, load `.env` first. If the file is missing or required keys are absent, report that fact and stop — do not instantiate clients.

## Submit workflow

1. Ensure the DLC `user_command` can access code, checkpoints, and datasets on the mounted storage paths declared in the config `data_sources`.
2. Add a short preflight block at the start of non-trivial `user_command` payloads: print hostname, rank/world size, working directory, key input paths, and cache-related env vars. Fail fast when required files or directories are missing. Do not print secrets.
3. Dry-run before every live submit:

```bash
uv run scripts/dlc.py submit \
  --config_path /path/to/job.yaml \
  --display_name my-job-smoke \
  --user_command 'sleep 100' \
  --dry_run true
```

4. Verify dry-run output: `DisplayName`, `WorkspaceId`, `ResourceId`, `UserCommand`, `JobSpecs[0].Image`, pod count, and CPU/GPU/memory config. If any field is wrong, fix the config or command before live submit.
5. Live submit (omit `--dry_run` or set it false):

```bash
uv run scripts/dlc.py submit \
  --config_path /path/to/job.yaml \
  --display_name my-job-smoke \
  --user_command 'sleep 100'
```

6. If a live job was launched with a bad config and has not done meaningful work, stop it before relaunching.

## Inspect and stop

```bash
uv run scripts/dlc.py status dlc-job-id
uv run scripts/dlc.py logs dlc-job-id --max_lines 200
uv run scripts/dlc.py logs dlc-job-id --pod_id dlc-job-id-master-0
uv run scripts/dlc.py events dlc-job-id
uv run scripts/dlc.py metrics dlc-job-id
uv run scripts/dlc.py metrics dlc-job-id --metric_type GpuMemoryUsage --time_step 60
uv run scripts/dlc.py stop dlc-job-id
```

After submission, check `status`, `events`, and logs from each pod. On distributed jobs, useful stack traces may appear only on worker pods.

`status` returns safe fields only: job id, display name, status, command, workspace, resource id, image, and resource config — never credentials.

## Config fields

`example.yaml` documents the draccus config accepted by `submit`:

| Field                  | Purpose                      |
| ---------------------- | ---------------------------- |
| `region_id`            | Aliyun region                |
| `workspace_id`         | PAI workspace                |
| `resource_id`          | Prepaid quota resource       |
| `display_name`         | Job label                    |
| `image`                | Container image              |
| `user_command`         | Shell command run in the job |
| `priority`             | 1–9                          |
| `cpu`, `memory`, `gpu` | Per-pod resources            |
| `pod_count`            | Number of pods               |
| `data_sources`         | OSS/CPFS mount list          |

CLI flags override YAML values. `submit` remains the default verb when no verb is given.
