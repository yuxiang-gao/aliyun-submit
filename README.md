# aliyun-submit

Agent skill for submitting and managing Alibaba Cloud PAI DLC jobs. Includes [`scripts/dlc.py`](scripts/dlc.py) (uv script CLI) and [`example.yaml`](example.yaml) (job config template).

## Install

```bash
npx skills add yuxiang-gao/aliyun-submit -g -y
```

Use `-g` for a global install; omit it for project-local. See [skills.sh](https://skills.sh/) for more.

## Setup

1. Install [uv](https://docs.astral.sh/uv/).
2. Add a `.env` in your project:

```env
ALIBABA_CLOUD_ACCESS_KEY_ID=...
ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
ALIYUN_PAI_WORKSPACE_ID=...
ALIYUN_PAI_RESOURCE_ID=...
ALIYUN_REGION_ID=cn-beijing
```

3. Copy `example.yaml`, fill in image, mounts, and resource specs.

## Quick start

1. Install the skill (above) and restart your agent session if needed.
2. In your training project, add `.env` credentials and a job config YAML (see Setup).
3. Ask your agent to submit or manage DLC jobs in plain language. For example:

   - "Launch my training run on Aliyun DLC using `job.yaml`, 4 pods."
   - "Why did DLC job `dlc-xxxxx` fail? Check its logs and events."
   - "Show GPU utilization for job `dlc-xxxxx`."
   - "Stop job `dlc-xxxxx`."

The agent loads [`SKILL.md`](SKILL.md) and uses the bundled `scripts/dlc.py` on your behalf. Mention Aliyun, PAI DLC, or job submission to trigger it in agents that auto-select skills.
