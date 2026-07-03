#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "alibabacloud-credentials>=1.0.8",
#   "alibabacloud-pai-dlc20201203==1.4.17",
#   "alibabacloud-tea-openapi>=0.4.4",
#   "draccus",
#   "python-dotenv>=1.2.2",
# ]
# ///
"""Submit, inspect, and stop Aliyun PAI DLC jobs through the Python SDK."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import draccus

COMMAND_NAMES = {"submit", "status", "logs", "events", "metrics", "stop"}
METRIC_TYPES = (
    "GpuCoreUsage",
    "GpuMemoryUsage",
    "CpuCoreUsage",
    "MemoryUsage",
    "NetworkInputRate",
    "NetworkOutputRate",
    "DiskReadRate",
    "DiskWriteRate",
)
SAFE_JOB_FIELDS = (
    "JobId",
    "DisplayName",
    "Status",
    "SubStatus",
    "ReasonCode",
    "ReasonMessage",
    "WorkspaceId",
    "ResourceId",
    "JobType",
    "UserCommand",
    "GmtCreateTime",
    "GmtFinishTime",
)
SAFE_JOB_SPEC_FIELDS = ("Type", "Image", "PodCount", "ResourceConfig")
SAFE_POD_FIELDS = ("PodId", "PodUid", "Status", "SubStatus", "Message", "GmtCreateTime", "GmtFinishTime")
_UV_RUN_HINT = "run this script with `uv run scripts/dlc.py ...`"


@dataclass(frozen=True)
class AliyunPaiDataSourceMount:
    data_source_id: str
    mount_path: str
    options: str | None = None


@dataclass(frozen=True)
class AliyunPaiJobConfig:
    region_id: str = field(default_factory=lambda: os.environ.get("ALIYUN_REGION_ID", "cn-beijing"))
    workspace_id: str | None = field(default_factory=lambda: os.environ.get("ALIYUN_PAI_WORKSPACE_ID"))
    resource_id: str | None = field(default_factory=lambda: os.environ.get("ALIYUN_PAI_RESOURCE_ID"))
    display_name: str | None = None
    image: str | None = None
    user_command: str | None = None
    job_type: str = "PyTorchJob"
    pod_count: int = 1
    role_type: str = "Worker"
    priority: int | None = None
    cpu: int | None = None
    memory: str | None = None
    gpu: int | None = None
    envs: dict[str, str] = field(default_factory=dict)
    data_sources: list[AliyunPaiDataSourceMount] = field(default_factory=list)
    dry_run: bool = False


def endpoint_for_region(region_id: str) -> str:
    return f"pai-dlc.{region_id}.aliyuncs.com"


def default_env_path() -> Path:
    return Path.cwd() / ".env"


def load_dotenv_file(env_path: Path | None = None) -> None:
    try:
        from dotenv import load_dotenv  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(_UV_RUN_HINT) from exc

    load_dotenv(dotenv_path=env_path or default_env_path())


def _to_map(value: object) -> dict[str, Any]:
    if hasattr(value, "to_map"):
        return value.to_map()
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"expected SDK object or mapping, got {type(value).__name__}")


def _pick_fields(source: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {field_name: source[field_name] for field_name in fields if source.get(field_name) is not None}


def summarize_job_response(job_body: Mapping[str, Any] | object) -> dict[str, Any]:
    """Return safe operator-facing job fields without credential payloads."""
    body = _to_map(job_body)
    summary = _pick_fields(body, SAFE_JOB_FIELDS)

    job_specs = body.get("JobSpecs")
    if isinstance(job_specs, list):
        summary["JobSpecs"] = [
            _pick_fields(spec, SAFE_JOB_SPEC_FIELDS) for spec in job_specs if isinstance(spec, Mapping)
        ]

    pods = body.get("Pods")
    if isinstance(pods, list):
        summary["Pods"] = [_pick_fields(pod, SAFE_POD_FIELDS) for pod in pods if isinstance(pod, Mapping)]

    return summary


def pod_log_targets(job_body: Mapping[str, Any] | object, requested_pod_id: str | None) -> list[str]:
    body = _to_map(job_body)
    pods = body.get("Pods")
    pod_ids: list[str] = []
    if isinstance(pods, list):
        for pod in pods:
            if isinstance(pod, Mapping) and isinstance(pod.get("PodId"), str):
                pod_ids.append(pod["PodId"])
    if requested_pod_id is not None:
        if pod_ids and requested_pod_id not in pod_ids:
            raise ValueError(f"pod_id {requested_pod_id!r} is not present in job {body.get('JobId', '<unknown>')}")
        return [requested_pod_id]
    if not pod_ids:
        raise ValueError("job response has no pod ids; pass --pod_id explicitly")
    return pod_ids


def build_create_job_request_payload(cfg: AliyunPaiJobConfig) -> dict[str, object]:
    if cfg.pod_count < 1:
        raise ValueError("pod_count must be >= 1")
    if not cfg.workspace_id:
        raise ValueError("workspace_id is required")
    if not cfg.resource_id:
        raise ValueError("resource_id is required for prepaid resource quota jobs")
    if not cfg.display_name:
        raise ValueError("display_name is required")
    if not cfg.image:
        raise ValueError("image is required")
    if not cfg.user_command:
        raise ValueError("user_command is required")
    if cfg.priority is not None and not 1 <= cfg.priority <= 9:
        raise ValueError("priority must be between 1 and 9")

    spec: dict[str, object] = {
        "Type": cfg.role_type,
        "Image": cfg.image,
        "PodCount": cfg.pod_count,
    }

    resource_config: dict[str, str] = {}
    if cfg.cpu is not None:
        resource_config["CPU"] = str(cfg.cpu)
    if cfg.memory:
        resource_config["Memory"] = cfg.memory
    if cfg.gpu is not None:
        resource_config["GPU"] = str(cfg.gpu)
    if not resource_config:
        raise ValueError("quota jobs require at least one resource config field")
    spec["ResourceConfig"] = resource_config

    payload: dict[str, object] = {
        "ResourceId": cfg.resource_id,
        "WorkspaceId": cfg.workspace_id,
        "DisplayName": cfg.display_name,
        "JobType": cfg.job_type,
        "JobSpecs": [spec],
        "UserCommand": cfg.user_command,
    }
    if cfg.envs:
        payload["Envs"] = dict(cfg.envs)
    if cfg.priority is not None:
        payload["Priority"] = cfg.priority
    if cfg.data_sources:
        data_sources: list[dict[str, str]] = []
        for data_source in cfg.data_sources:
            item = {
                "DataSourceId": data_source.data_source_id,
                "MountPath": data_source.mount_path,
            }
            if data_source.options:
                item["Options"] = data_source.options
            data_sources.append(item)
        payload["DataSources"] = data_sources
    return payload


def make_dlc_client(region_id: str) -> object:
    try:
        from alibabacloud_credentials.client import Client as CredClient  # noqa: PLC0415
        from alibabacloud_pai_dlc20201203.client import Client as DLCClient  # noqa: PLC0415
        from alibabacloud_tea_openapi.models import Config  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(_UV_RUN_HINT) from exc

    return DLCClient(
        config=Config(
            credential=CredClient(),
            region_id=region_id,
            endpoint=endpoint_for_region(region_id),
        )
    )


def submit_job(cfg: AliyunPaiJobConfig) -> str:
    from alibabacloud_pai_dlc20201203.models import CreateJobRequest  # noqa: PLC0415

    client = make_dlc_client(cfg.region_id)
    request = CreateJobRequest().from_map(build_create_job_request_payload(cfg))
    response = client.create_job(request)
    return response.body.job_id


def parse_config(args: Sequence[str] | None = None, env_path: Path | None = None) -> AliyunPaiJobConfig:
    load_dotenv_file(env_path=env_path)
    return draccus.parse(config_class=AliyunPaiJobConfig, args=args)


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _region_from_args(region_id: str | None) -> str:
    return region_id or os.environ.get("ALIYUN_REGION_ID", "cn-beijing")


def _get_job_body(client: object, job_id: str, need_detail: bool = True) -> dict[str, Any]:
    from alibabacloud_pai_dlc20201203.models import GetJobRequest  # noqa: PLC0415

    response = client.get_job(job_id, GetJobRequest(need_detail=need_detail))
    return _to_map(response.body)


def _add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--region_id", default=None, help="Aliyun region id; defaults to ALIYUN_REGION_ID or cn-beijing"
    )
    parser.add_argument("--env_path", type=Path, default=None, help="dotenv path; defaults to ./.env in the cwd")


def _run_submit(args: Sequence[str]) -> None:
    cfg = parse_config(args)
    if cfg.dry_run:
        _print_json(build_create_job_request_payload(cfg))
        return
    job_id = submit_job(cfg)
    _print_json({"JobId": job_id})


def _run_status(args: Sequence[str]) -> None:
    parser = argparse.ArgumentParser(prog=f"{Path(__file__).name} status")
    _add_runtime_args(parser)
    parser.add_argument("job_id")
    parser.add_argument("--brief", action="store_true", help="omit pod/job detail from the SDK request")
    parsed = parser.parse_args(args)

    load_dotenv_file(parsed.env_path)
    client = make_dlc_client(_region_from_args(parsed.region_id))
    _print_json(summarize_job_response(_get_job_body(client, parsed.job_id, need_detail=not parsed.brief)))


def _run_logs(args: Sequence[str]) -> None:
    from alibabacloud_pai_dlc20201203.models import GetPodLogsRequest  # noqa: PLC0415

    parser = argparse.ArgumentParser(prog=f"{Path(__file__).name} logs")
    _add_runtime_args(parser)
    parser.add_argument("job_id")
    parser.add_argument("--pod_id", default=None, help="pod id; defaults to every pod in the job")
    parser.add_argument("--pod_uid", default=None, help="optional Aliyun pod uid")
    parser.add_argument("--max_lines", type=int, default=200)
    parser.add_argument("--start_time", default=None)
    parser.add_argument("--end_time", default=None)
    parsed = parser.parse_args(args)

    load_dotenv_file(parsed.env_path)
    client = make_dlc_client(_region_from_args(parsed.region_id))
    job_body = _get_job_body(client, parsed.job_id)
    for pod_id in pod_log_targets(job_body, requested_pod_id=parsed.pod_id):
        request = GetPodLogsRequest(
            max_lines=parsed.max_lines,
            pod_uid=parsed.pod_uid,
            start_time=parsed.start_time,
            end_time=parsed.end_time,
        )
        response = client.get_pod_logs(parsed.job_id, pod_id, request)
        body = _to_map(response.body)
        print(f"===== {pod_id} =====")
        logs = body.get("Logs")
        if isinstance(logs, list):
            print("\n".join(str(line) for line in logs))
        else:
            _print_json(body)


def _run_events(args: Sequence[str]) -> None:
    from alibabacloud_pai_dlc20201203.models import GetJobEventsRequest, GetPodEventsRequest  # noqa: PLC0415

    parser = argparse.ArgumentParser(prog=f"{Path(__file__).name} events")
    _add_runtime_args(parser)
    parser.add_argument("job_id")
    parser.add_argument("--pod_id", default=None, help="pod id; omit for job-level events")
    parser.add_argument("--pod_uid", default=None, help="optional Aliyun pod uid")
    parser.add_argument("--max_events_num", type=int, default=100)
    parser.add_argument("--start_time", default=None)
    parser.add_argument("--end_time", default=None)
    parsed = parser.parse_args(args)

    load_dotenv_file(parsed.env_path)
    client = make_dlc_client(_region_from_args(parsed.region_id))
    if parsed.pod_id is None:
        request = GetJobEventsRequest(
            max_events_num=parsed.max_events_num,
            start_time=parsed.start_time,
            end_time=parsed.end_time,
        )
        body = _to_map(client.get_job_events(parsed.job_id, request).body)
        _print_json(body)
        return

    request = GetPodEventsRequest(
        max_events_num=parsed.max_events_num,
        pod_uid=parsed.pod_uid,
        start_time=parsed.start_time,
        end_time=parsed.end_time,
    )
    body = _to_map(client.get_pod_events(parsed.job_id, parsed.pod_id, request).body)
    _print_json(body)


def _run_metrics(args: Sequence[str]) -> None:
    from alibabacloud_pai_dlc20201203.models import GetJobMetricsRequest  # noqa: PLC0415

    parser = argparse.ArgumentParser(prog=f"{Path(__file__).name} metrics")
    _add_runtime_args(parser)
    parser.add_argument("job_id")
    parser.add_argument("--metric_type", choices=METRIC_TYPES, default="GpuCoreUsage")
    parser.add_argument("--time_step", default=None)
    parser.add_argument("--start_time", default=None)
    parser.add_argument("--end_time", default=None)
    parser.add_argument("--token", default=None)
    parsed = parser.parse_args(args)

    load_dotenv_file(parsed.env_path)
    client = make_dlc_client(_region_from_args(parsed.region_id))
    request = GetJobMetricsRequest(
        metric_type=parsed.metric_type,
        time_step=parsed.time_step,
        start_time=parsed.start_time,
        end_time=parsed.end_time,
        token=parsed.token,
    )
    _print_json(_to_map(client.get_job_metrics(parsed.job_id, request).body))


def _run_stop(args: Sequence[str]) -> None:
    parser = argparse.ArgumentParser(prog=f"{Path(__file__).name} stop")
    _add_runtime_args(parser)
    parser.add_argument("job_id")
    parsed = parser.parse_args(args)

    load_dotenv_file(parsed.env_path)
    client = make_dlc_client(_region_from_args(parsed.region_id))
    response = client.stop_job(parsed.job_id)
    _print_json(_to_map(response.body))


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.WARNING)
    args = list(sys.argv[1:] if argv is None else argv)
    command = args.pop(0) if args and args[0] in COMMAND_NAMES else "submit"
    if command == "submit":
        _run_submit(args)
    elif command == "status":
        _run_status(args)
    elif command == "logs":
        _run_logs(args)
    elif command == "events":
        _run_events(args)
    elif command == "metrics":
        _run_metrics(args)
    elif command == "stop":
        _run_stop(args)
    else:
        raise ValueError(f"unknown command: {command}")


if __name__ == "__main__":
    main()
