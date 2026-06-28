#!/usr/bin/env python3
"""deploy_web.py — web/ SPA 를 S3(비공개) + CloudFront(OAC) 로 배포 (boto3).

순서: [1] S3 버킷(비공개) · [2] OAC + CloudFront 배포 · [3] 버킷 정책(CloudFront 만 read) ·
      [4] web 빌드(VITE_API_BASE=BRIEFING_API_URL) · [5] dist→S3 업로드 · [6] invalidation · [7] .env writeback.
사전: deploy_api.py 완료(.env 의 BRIEFING_API_URL). 사용법: `uv run python -m briefing.webapi.deploy_web`
"""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import time
from pathlib import Path

import boto3

from ..runtime.deploy_runtime import _upsert_env_lines
from ..shared.config import load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
WEB_DIR = PROJECT_ROOT / "web"
DIST_DIR = WEB_DIR / "dist"
ENV_SECTION = "# ④ Briefing Web (deploy_web.py)"
OAC_NAME = "briefing-web-oac"
_G, _Y, _B, _R, _NC = "\033[0;32m", "\033[1;33m", "\033[0;34m", "\033[0;31m", "\033[0m"


def _ensure_bucket(s3, bucket, region) -> None:
    try:
        kw = {} if region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": region}}
        s3.create_bucket(Bucket=bucket, **kw)
        print(f"   S3 버킷 생성: {bucket}")
    except (s3.exceptions.BucketAlreadyOwnedByYou, s3.exceptions.BucketAlreadyExists):
        print(f"   S3 버킷 존재(재사용): {bucket}")
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": False, "RestrictPublicBuckets": False,   # CloudFront SourceArn 정책 허용
        },
    )


def _ensure_oac(cf) -> str:
    for it in cf.list_origin_access_controls().get("OriginAccessControlList", {}).get("Items", []):
        if it["Name"] == OAC_NAME:
            return it["Id"]
    return cf.create_origin_access_control(OriginAccessControlConfig={
        "Name": OAC_NAME, "SigningProtocol": "sigv4", "SigningBehavior": "always",
        "OriginAccessControlOriginType": "s3",
    })["OriginAccessControl"]["Id"]


def _ensure_distribution(cf, bucket, region, oac_id) -> tuple[str, str]:
    """기존 코멘트=bucket 인 배포 재사용, 없으면 생성. SPA 라우팅: 403/404→/index.html 200."""
    for d in cf.list_distributions().get("DistributionList", {}).get("Items", []):
        if d.get("Comment") == bucket:
            return d["Id"], d["DomainName"]
    origin_domain = f"{bucket}.s3.{region}.amazonaws.com"
    ref = bucket                                              # CallerReference(멱등 키)
    cfg = {
        "CallerReference": ref, "Comment": bucket, "Enabled": True, "DefaultRootObject": "index.html",
        "Origins": {"Quantity": 1, "Items": [{
            "Id": "s3origin", "DomainName": origin_domain,
            "S3OriginConfig": {"OriginAccessIdentity": ""}, "OriginAccessControlId": oac_id,
        }]},
        "DefaultCacheBehavior": {
            "TargetOriginId": "s3origin", "ViewerProtocolPolicy": "redirect-to-https",
            "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",  # AWS Managed-CachingOptimized
            "Compress": True,
        },
        "CustomErrorResponses": {"Quantity": 2, "Items": [
            {"ErrorCode": 403, "ResponseCode": "200", "ResponsePagePath": "/index.html", "ErrorCachingMinTTL": 10},
            {"ErrorCode": 404, "ResponseCode": "200", "ResponsePagePath": "/index.html", "ErrorCachingMinTTL": 10},
        ]},
    }
    d = cf.create_distribution(DistributionConfig=cfg)["Distribution"]
    print(f"   CloudFront 배포 생성: {d['Id']} (전파 ~15분)")
    return d["Id"], d["DomainName"]


def _put_bucket_policy(s3, bucket, acct, dist_id) -> None:
    policy = {"Version": "2012-10-17", "Statement": [{
        "Sid": "AllowCloudFrontRead", "Effect": "Allow",
        "Principal": {"Service": "cloudfront.amazonaws.com"},
        "Action": "s3:GetObject", "Resource": f"arn:aws:s3:::{bucket}/*",
        "Condition": {"StringEquals": {"AWS:SourceArn": f"arn:aws:cloudfront::{acct}:distribution/{dist_id}"}},
    }]}
    s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))


def _build_web(api_url) -> None:
    env = {**os.environ, "VITE_API_BASE": api_url}
    subprocess.run(["npm", "install"], cwd=WEB_DIR, check=True)
    subprocess.run(["npm", "run", "build"], cwd=WEB_DIR, check=True, env=env)


def _sync_dist(s3, bucket) -> None:
    for p in sorted(DIST_DIR.rglob("*")):
        if not p.is_file():
            continue
        key = str(p.relative_to(DIST_DIR))
        ctype = mimetypes.guess_type(key)[0] or "application/octet-stream"
        s3.upload_file(str(p), bucket, key, ExtraArgs={"ContentType": ctype})
    print(f"   업로드 완료: {bucket}")


def main() -> None:
    settings = load_settings()
    region = settings.region
    api_url = os.getenv("BRIEFING_API_URL", "")
    if not api_url:
        sys.exit(f"{_R}❌ BRIEFING_API_URL 미설정 — deploy_api.py 먼저{_NC}")
    acct = boto3.client("sts").get_caller_identity()["Account"]
    bucket = f"briefing-web-{acct}-{region}"
    print(f"\n{_B}{'=' * 60}\n  ④ Web 배포 — bucket={bucket}\n{'=' * 60}{_NC}\n")

    s3 = boto3.client("s3", region_name=region)
    cf = boto3.client("cloudfront")

    print(f"{_Y}[1/6] S3 버킷(비공개){_NC}")
    _ensure_bucket(s3, bucket, region)
    print(f"{_Y}[2/6] OAC + CloudFront 배포{_NC}")
    oac_id = _ensure_oac(cf)
    dist_id, domain = _ensure_distribution(cf, bucket, region, oac_id)
    print(f"{_Y}[3/6] 버킷 정책(CloudFront read){_NC}")
    _put_bucket_policy(s3, bucket, acct, dist_id)
    print(f"{_Y}[4/6] web 빌드(VITE_API_BASE={api_url}){_NC}")
    _build_web(api_url)
    print(f"{_Y}[5/6] dist → S3 업로드{_NC}")
    _sync_dist(s3, bucket)
    print(f"{_Y}[6/6] CloudFront invalidation{_NC}")
    cf.create_invalidation(DistributionId=dist_id,
                           InvalidationBatch={"Paths": {"Quantity": 1, "Items": ["/*"]},
                                              "CallerReference": str(time.time_ns())})

    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    ENV_FILE.write_text(_upsert_env_lines(text, {
        "BRIEFING_WEB_BUCKET": bucket,
        "BRIEFING_CF_DIST_ID": dist_id,
        "BRIEFING_WEB_URL": f"https://{domain}",
    }, section=ENV_SECTION), encoding="utf-8")

    print(f"\n{_B}{'=' * 60}{_NC}\n{_G}  ④ Web 배포 완료{_NC}")
    print(f"   사이트: https://{domain}  (전파 ~15분 후 안정)")
    print(f"   API:    {api_url}/catalog\n")


if __name__ == "__main__":
    main()
