from __future__ import annotations

import argparse
import base64
import concurrent.futures
import dataclasses
import gzip
import hashlib
import json
import math
import os
import platform
import random
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

import httpx
import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCES = ROOT / "configs" / "sources.yaml"
DEFAULT_OUTPUT = ROOT / "outputs"
DEFAULT_TOOLS = ROOT / "tools"
DEFAULT_RUNTIME = ROOT / "runtime"

USER_AGENT = "quality-node-forge/0.1 (+https://github.com/MetaCubeX/mihomo)"
BAD_NAME_RE = re.compile(
    r"(\u5269\u4f59|\u6d41\u91cf|\u5957\u9910|\u5b98\u7f51|\u8ba2\u9605|\u5230\u671f|"
    r"\u8fc7\u671f|\u7fa4\u7ec4|\u9891\u9053|\u5173\u6ce8|\u7f51\u5740|\u5ba2\u670d|"
    r"\u66f4\u65b0|\u516c\u544a|\u91cd\u7f6e|\u500d\u7387|\u6d4b\u8bd5|expire|"
    r"traffic|telegram|tg|channel|official|website|test)",
    re.IGNORECASE,
)
URI_RE = re.compile(
    r"(?P<uri>(?:ss|ssr|vmess|vless|trojan|hysteria2|hy2|tuic)://[^\s<>'\"`|]+)",
    re.IGNORECASE,
)
SUPPORTED_TYPES = {
    "ss",
    "ssr",
    "vmess",
    "vless",
    "trojan",
    "hysteria",
    "hysteria2",
    "tuic",
}
PREFERRED_TYPES = {"vless", "trojan", "hysteria2", "ss"}


@dataclasses.dataclass(slots=True)
class Source:
    name: str
    url: str
    weight: float
    enabled: bool = True
    notes: str = ""


@dataclasses.dataclass(slots=True)
class Candidate:
    proxy: dict[str, Any]
    source: str
    source_weight: float
    fingerprint: str
    pre_score: float


@dataclasses.dataclass(slots=True)
class TestResult:
    name: str
    source: str
    proxy_type: str
    avg_delay: float | None
    min_delay: float | None
    max_delay: float | None
    jitter: float | None
    success_count: int
    total_count: int
    score: float
    error: str | None
    proxy: dict[str, Any]

    @property
    def success_rate(self) -> float:
        if self.total_count <= 0:
            return 0.0
        return self.success_count / self.total_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="quality-node-forge",
        description="Build a small high-quality Clash/Mihomo subscription.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="fetch, test, rank and emit subscription")
    run.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    run.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    run.add_argument("--tools", type=Path, default=DEFAULT_TOOLS)
    run.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    run.add_argument("--top", type=int, default=30)
    run.add_argument("--candidate-limit", type=int, default=260)
    run.add_argument("--rounds", type=int, default=3)
    run.add_argument("--timeout-ms", type=int, default=5000)
    run.add_argument("--max-delay-ms", type=int, default=1800)
    run.add_argument("--max-jitter-ms", type=int, default=700)
    run.add_argument("--min-success-rate", type=float, default=1.0)
    run.add_argument("--workers", type=int, default=18)
    run.add_argument(
        "--probe-url",
        action="append",
        default=None,
        help="Probe URL. Can be provided multiple times.",
    )
    run.add_argument("--skip-test", action="store_true", help="emit prefiltered nodes without mihomo testing")
    run.set_defaults(func=run_pipeline)

    args = parser.parse_args(argv)
    return args.func(args)


def run_pipeline(args: argparse.Namespace) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    args.tools.mkdir(parents=True, exist_ok=True)
    args.runtime.mkdir(parents=True, exist_ok=True)

    sources = load_sources(args.sources)
    print(f"[1/6] enabled sources: {len(sources)}", flush=True)

    fetched = fetch_sources(sources)
    print(f"[2/6] fetched sources: {sum(1 for item in fetched if item[1])}/{len(fetched)}", flush=True)

    candidates = collect_candidates(fetched)
    print(f"[3/6] unique clean candidates: {len(candidates)}", flush=True)
    if not candidates:
        raise SystemExit("No valid proxy candidates found.")

    candidates = sorted(candidates, key=lambda c: c.pre_score, reverse=True)[: args.candidate_limit]
    rename_candidates(candidates)
    print(f"[4/6] candidates selected for testing: {len(candidates)}", flush=True)

    if args.skip_test:
        results = [
            TestResult(
                name=c.proxy["name"],
                source=c.source,
                proxy_type=str(c.proxy.get("type", "")),
                avg_delay=None,
                min_delay=None,
                max_delay=None,
                jitter=None,
                success_count=0,
                total_count=0,
                score=c.pre_score,
                error=None,
                proxy=c.proxy,
            )
            for c in candidates
        ]
    else:
        mihomo = ensure_mihomo(args.tools)
        print(f"[5/6] mihomo: {mihomo}", flush=True)
        probe_urls = args.probe_url or [
            "https://www.gstatic.com/generate_204",
            "https://cp.cloudflare.com/generate_204",
            "https://www.apple.com/library/test/success.html",
        ]
        results = test_with_mihomo(
            mihomo=mihomo,
            runtime=args.runtime,
            candidates=candidates,
            rounds=args.rounds,
            timeout_ms=args.timeout_ms,
            workers=args.workers,
            probe_urls=probe_urls,
        )

    winners = select_winners(results, args.top, args.max_delay_ms, args.max_jitter_ms, args.min_success_rate)
    print(f"[6/6] winners: {len(winners)}", flush=True)
    emit_outputs(args.out, winners, results, sources, args)
    return 0


def load_sources(path: Path) -> list[Source]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources: list[Source] = []
    for raw in data.get("sources", []):
        if raw.get("enabled", True):
            sources.append(
                Source(
                    name=str(raw["name"]),
                    url=str(raw["url"]),
                    weight=float(raw.get("weight", 1.0)),
                    enabled=True,
                    notes=str(raw.get("notes", "")),
                )
            )
    return sources


def fetch_sources(sources: list[Source]) -> list[tuple[Source, str | None, str | None]]:
    def fetch_one(source: Source) -> tuple[Source, str | None, str | None]:
        try:
            with httpx.Client(
                timeout=httpx.Timeout(35.0, connect=12.0),
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                resp = client.get(source.url)
                resp.raise_for_status()
                text = resp.content.decode("utf-8", errors="replace")
                if len(text.strip()) < 20:
                    return source, None, "empty response"
                return source, text, None
        except Exception as exc:  # noqa: BLE001
            return source, None, str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(sources) or 1)) as pool:
        return list(pool.map(fetch_one, sources))


def collect_candidates(fetched: list[tuple[Source, str | None, str | None]]) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for source, text, error in fetched:
        if error:
            print(f"  source failed: {source.name}: {error}", flush=True)
            continue
        proxies = parse_source_proxies(text or "")
        print(f"  {source.name}: {len(proxies)} proxies", flush=True)
        for proxy in proxies:
            normalized = normalize_proxy(proxy)
            if not normalized:
                continue
            fp = proxy_fingerprint(normalized)
            if fp in seen:
                continue
            seen.add(fp)
            score = pre_score_proxy(normalized, source.weight)
            candidates.append(
                Candidate(
                    proxy=normalized,
                    source=source.name,
                    source_weight=source.weight,
                    fingerprint=fp,
                    pre_score=score,
                )
            )
    return candidates


def parse_source_proxies(text: str) -> list[dict[str, Any]]:
    proxies = parse_clash_proxies(text)
    for body in expand_subscription_texts(text):
        proxies.extend(parse_uri_proxies(body))
    return proxies


def parse_clash_proxies(text: str) -> list[dict[str, Any]]:
    try:
        data = yaml.safe_load(text)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    proxies = data.get("proxies")
    if isinstance(proxies, list):
        return [p for p in proxies if isinstance(p, dict)]
    return []


def expand_subscription_texts(text: str) -> list[str]:
    bodies = [text]
    decoded = decode_base64_text(text)
    if decoded and decoded not in bodies:
        bodies.append(decoded)
    return bodies


def decode_base64_text(text: str) -> str | None:
    compact = re.sub(r"\s+", "", urllib.parse.unquote(text.strip()))
    if len(compact) < 24 or not re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
        return None
    padded = compact + ("=" * ((4 - len(compact) % 4) % 4))
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception:
        return None
    decoded = raw.decode("utf-8", errors="replace")
    return decoded if "://" in decoded else None


def parse_uri_proxies(text: str) -> list[dict[str, Any]]:
    proxies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in URI_RE.finditer(text):
        uri = match.group("uri").strip().rstrip("),];")
        if uri in seen:
            continue
        seen.add(uri)
        proxy = parse_proxy_uri(uri)
        if proxy:
            proxies.append(proxy)
    return proxies


def parse_proxy_uri(uri: str) -> dict[str, Any] | None:
    scheme = uri.split("://", 1)[0].lower()
    try:
        if scheme == "vmess":
            return parse_vmess_uri(uri)
        if scheme == "vless":
            return parse_vless_uri(uri)
        if scheme == "trojan":
            return parse_trojan_uri(uri)
        if scheme == "ss":
            return parse_ss_uri(uri)
        if scheme in {"hysteria2", "hy2"}:
            return parse_hysteria2_uri(uri)
    except Exception:
        return None
    return None


def b64decode_loose(value: str) -> str | None:
    compact = re.sub(r"\s+", "", value)
    padded = compact + ("=" * ((4 - len(compact) % 4) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        try:
            return base64.b64decode(padded.encode("ascii"), validate=False).decode("utf-8", errors="replace")
        except Exception:
            return None


def parse_vmess_uri(uri: str) -> dict[str, Any] | None:
    body = uri.split("://", 1)[1]
    decoded = b64decode_loose(body)
    if not decoded:
        return None
    data = json.loads(decoded)
    server = str(data.get("add", "")).strip()
    port = int(data.get("port", 0))
    uuid = str(data.get("id", "")).strip()
    if not server or not port or not uuid:
        return None
    proxy: dict[str, Any] = {
        "name": str(data.get("ps") or f"vmess-{server}-{port}"),
        "type": "vmess",
        "server": server,
        "port": port,
        "uuid": uuid,
        "alterId": int(data.get("aid") or 0),
        "cipher": str(data.get("scy") or "auto"),
        "udp": True,
    }
    network = str(data.get("net") or "").lower()
    if network and network != "tcp":
        proxy["network"] = network
    tls = str(data.get("tls") or "").lower()
    if tls == "tls":
        proxy["tls"] = True
        sni = str(data.get("sni") or data.get("host") or "").strip()
        if sni:
            proxy["servername"] = sni
    if network == "ws":
        ws_opts: dict[str, Any] = {"path": str(data.get("path") or "/")}
        host = str(data.get("host") or "").strip()
        if host:
            ws_opts["headers"] = {"Host": host}
        proxy["ws-opts"] = ws_opts
    elif network == "grpc":
        service = str(data.get("path") or "").strip()
        if service:
            proxy["grpc-opts"] = {"grpc-service-name": service}
    return proxy


def parse_vless_uri(uri: str) -> dict[str, Any] | None:
    parts = urllib.parse.urlsplit(uri)
    uuid = urllib.parse.unquote(parts.username or "").strip()
    server = parts.hostname or ""
    port = int(parts.port or 0)
    if not uuid or not server or not port:
        return None
    query = qs(parts.query)
    proxy: dict[str, Any] = {
        "name": uri_name(parts.fragment, "vless", server, port),
        "type": "vless",
        "server": server,
        "port": port,
        "uuid": uuid,
        "udp": True,
    }
    flow = query.get("flow")
    if flow:
        proxy["flow"] = flow
    security = (query.get("security") or "").lower()
    if security in {"tls", "reality"}:
        proxy["tls"] = True
    sni = query.get("sni") or query.get("servername")
    if sni:
        proxy["servername"] = sni
    fp = query.get("fp")
    if fp:
        proxy["client-fingerprint"] = fp
    if security == "reality":
        reality: dict[str, Any] = {}
        if query.get("pbk"):
            reality["public-key"] = query["pbk"]
        if query.get("sid"):
            reality["short-id"] = query["sid"]
        if reality:
            proxy["reality-opts"] = reality
    add_transport_opts(proxy, query)
    return proxy


def parse_trojan_uri(uri: str) -> dict[str, Any] | None:
    parts = urllib.parse.urlsplit(uri)
    password = urllib.parse.unquote(parts.username or "").strip()
    server = parts.hostname or ""
    port = int(parts.port or 0)
    if not password or not server or not port:
        return None
    query = qs(parts.query)
    proxy: dict[str, Any] = {
        "name": uri_name(parts.fragment, "trojan", server, port),
        "type": "trojan",
        "server": server,
        "port": port,
        "password": password,
        "udp": True,
    }
    sni = query.get("sni") or query.get("peer") or query.get("servername")
    if sni:
        proxy["sni"] = sni
    if query.get("allowInsecure") in {"1", "true"} or query.get("insecure") in {"1", "true"}:
        proxy["skip-cert-verify"] = True
    add_transport_opts(proxy, query)
    return proxy


def parse_ss_uri(uri: str) -> dict[str, Any] | None:
    body = uri.split("://", 1)[1]
    name = ""
    if "#" in body:
        body, fragment = body.split("#", 1)
        name = urllib.parse.unquote(fragment)
    if "?" in body:
        body, _query = body.split("?", 1)
    if "@" not in body:
        decoded = b64decode_loose(body)
        if not decoded:
            return None
        body = decoded
    userinfo, hostport = body.rsplit("@", 1)
    userinfo = urllib.parse.unquote(userinfo)
    if ":" not in userinfo:
        decoded_user = b64decode_loose(userinfo)
        if decoded_user:
            userinfo = decoded_user
    if ":" not in userinfo:
        return None
    cipher, password = userinfo.split(":", 1)
    server, port = split_host_port(hostport)
    if not cipher or not password or not server or not port:
        return None
    return {
        "name": name or f"ss-{server}-{port}",
        "type": "ss",
        "server": server,
        "port": port,
        "cipher": cipher,
        "password": password,
        "udp": True,
    }


def parse_hysteria2_uri(uri: str) -> dict[str, Any] | None:
    parts = urllib.parse.urlsplit(uri.replace("hy2://", "hysteria2://", 1))
    password = urllib.parse.unquote(parts.username or "").strip()
    server = parts.hostname or ""
    port = int(parts.port or 0)
    if not password or not server or not port:
        return None
    query = qs(parts.query)
    proxy: dict[str, Any] = {
        "name": uri_name(parts.fragment, "hysteria2", server, port),
        "type": "hysteria2",
        "server": server,
        "port": port,
        "password": password,
    }
    sni = query.get("sni")
    if sni:
        proxy["sni"] = sni
    if query.get("insecure") in {"1", "true"}:
        proxy["skip-cert-verify"] = True
    if query.get("obfs"):
        proxy["obfs"] = query["obfs"]
    if query.get("obfs-password"):
        proxy["obfs-password"] = query["obfs-password"]
    return proxy


def qs(query: str) -> dict[str, str]:
    parsed = urllib.parse.parse_qs(query, keep_blank_values=True)
    return {k: urllib.parse.unquote(v[-1]) for k, v in parsed.items() if v}


def uri_name(fragment: str, p_type: str, server: str, port: int) -> str:
    name = urllib.parse.unquote(fragment or "").strip()
    return name or f"{p_type}-{server}-{port}"


def add_transport_opts(proxy: dict[str, Any], query: dict[str, str]) -> None:
    network = (query.get("type") or query.get("network") or "").lower()
    if not network or network in {"tcp", "raw"}:
        return
    proxy["network"] = network
    if network == "ws":
        ws_opts: dict[str, Any] = {"path": query.get("path") or "/"}
        host = query.get("host")
        if host:
            ws_opts["headers"] = {"Host": host}
        proxy["ws-opts"] = ws_opts
    elif network == "grpc":
        service = query.get("serviceName") or query.get("service-name")
        if service:
            proxy["grpc-opts"] = {"grpc-service-name": service}


def split_host_port(value: str) -> tuple[str, int]:
    parsed = urllib.parse.urlsplit("//" + value)
    return parsed.hostname or "", int(parsed.port or 0)


def normalize_proxy(proxy: dict[str, Any]) -> dict[str, Any] | None:
    p = json.loads(json.dumps(proxy, ensure_ascii=False))
    p_type = str(p.get("type", "")).lower().strip()
    if p_type not in SUPPORTED_TYPES:
        return None

    server = str(p.get("server", "")).strip()
    if not server or server.lower() in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return None
    if server.endswith(".local"):
        return None

    try:
        port = int(p.get("port"))
    except Exception:
        return None
    if port <= 0 or port > 65535:
        return None
    p["type"] = p_type
    p["server"] = server
    p["port"] = port
    normalize_required_fields(p)
    if not has_required_fields(p):
        return None
    if not clean_host_fields(p):
        return None

    name = str(p.get("name", "")).strip()
    if not name:
        name = f"{p_type}-{server}-{port}"
    name = sanitize_name(name)
    if BAD_NAME_RE.search(name):
        return None
    p["name"] = name
    return p


def normalize_required_fields(proxy: dict[str, Any]) -> None:
    p_type = str(proxy.get("type", ""))
    if p_type in {"vless", "vmess"} and not proxy.get("uuid") and proxy.get("password"):
        proxy["uuid"] = proxy["password"]
    if p_type == "trojan":
        if not proxy.get("password") and proxy.get("uuid"):
            proxy["password"] = proxy["uuid"]
        proxy.pop("uuid", None)


def has_required_fields(proxy: dict[str, Any]) -> bool:
    p_type = str(proxy.get("type", ""))
    if p_type in {"vless", "vmess"}:
        return bool(str(proxy.get("uuid") or "").strip())
    if p_type == "trojan":
        return bool(str(proxy.get("password") or "").strip())
    if p_type == "ss":
        return bool(str(proxy.get("cipher") or "").strip() and str(proxy.get("password") or "").strip())
    if p_type in {"hysteria", "hysteria2"}:
        return bool(str(proxy.get("password") or "").strip())
    return True


def clean_host_fields(proxy: dict[str, Any]) -> bool:
    for key in ("servername", "sni", "host"):
        if key not in proxy:
            continue
        value = str(proxy.get(key) or "").strip()
        if not value:
            proxy.pop(key, None)
            continue
        value = value.split("/", 1)[0].strip()
        if " " in value:
            return False
        proxy[key] = value
    ws_opts = proxy.get("ws-opts")
    if isinstance(ws_opts, dict):
        headers = ws_opts.get("headers")
        if isinstance(headers, dict) and "Host" in headers:
            host = str(headers.get("Host") or "").split("/", 1)[0].strip()
            if host:
                headers["Host"] = host
            else:
                headers.pop("Host", None)
    return True


def sanitize_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace("\u200b", "")
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"[^\w .:@()#+-]+", "", name, flags=re.UNICODE)
    return name[:80] or "node"


def proxy_fingerprint(proxy: dict[str, Any]) -> str:
    ignored = {"name", "udp", "interface-name", "routing-mark"}
    stable = {k: v for k, v in proxy.items() if k not in ignored}
    encoded = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def pre_score_proxy(proxy: dict[str, Any], source_weight: float) -> float:
    p_type = str(proxy.get("type", ""))
    score = 1000.0 * source_weight

    if p_type in PREFERRED_TYPES:
        score += 90
    if p_type == "vmess":
        score -= 60
    if p_type == "ssr":
        score -= 120

    name = str(proxy.get("name", ""))
    if BAD_NAME_RE.search(name):
        score -= 500
    if proxy.get("tls") is True:
        score += 70
    if proxy.get("reality-opts") or proxy.get("reality"):
        score += 110
    if proxy.get("network") in {"ws", "grpc", "h2", "http"}:
        score += 20
    if str(proxy.get("sni", "")).strip():
        score += 25
    if str(proxy.get("servername", "")).strip():
        score += 25

    return score


def rename_candidates(candidates: list[Candidate]) -> None:
    used: set[str] = set()
    for idx, c in enumerate(candidates, start=1):
        p_type = str(c.proxy.get("type", "node")).upper()
        source_tag = source_short_name(c.source)
        server = re.sub(r"[^A-Za-z0-9.-]+", "-", str(c.proxy.get("server", "node"))).strip("-")
        port = str(c.proxy.get("port", ""))
        base = f"{idx:03d}-{source_tag}-{p_type}-{server}-{port}"
        name = base[:90]
        suffix = 2
        while name in used:
            tail = f"-{suffix}"
            name = (base[: 90 - len(tail)] + tail)
            suffix += 1
        used.add(name)
        c.proxy["name"] = name


def source_short_name(source: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", source)
    if not words:
        return "SRC"
    return "".join(w[0].upper() for w in words[:3])[:5]


def ensure_mihomo(tools_dir: Path) -> Path:
    bin_dir = tools_dir / "mihomo"
    exe_name = "mihomo.exe" if os.name == "nt" else "mihomo"
    target = bin_dir / exe_name
    if target.exists():
        return target

    bin_dir.mkdir(parents=True, exist_ok=True)
    release = github_json("https://api.github.com/repos/MetaCubeX/mihomo/releases/latest")
    assets = release.get("assets", [])
    asset = choose_mihomo_asset(assets)
    if not asset:
        raise RuntimeError("Could not find a compatible mihomo release asset.")

    url = asset["browser_download_url"]
    download_path = bin_dir / asset["name"]
    download_file(url, download_path)
    digest = asset.get("digest")
    if isinstance(digest, str) and digest.startswith("sha256:"):
        actual = sha256_file(download_path)
        expected = digest.split(":", 1)[1]
        if actual.lower() != expected.lower():
            raise RuntimeError(f"mihomo checksum mismatch: {actual} != {expected}")

    if download_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(download_path) as zf:
            for member in zf.namelist():
                if member.lower().endswith(".exe"):
                    with zf.open(member) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    break
            else:
                raise RuntimeError("No executable found in mihomo zip.")
    elif download_path.suffix.lower() == ".gz":
        with gzip.open(download_path, "rb") as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    else:
        raise RuntimeError(f"Unsupported mihomo asset: {download_path.name}")

    if os.name != "nt":
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def github_json(url: str) -> dict[str, Any]:
    gh = find_gh()
    if gh and url.startswith("https://api.github.com/"):
        api_path = url.removeprefix("https://api.github.com/")
        try:
            raw = subprocess.check_output([str(gh), "api", api_path], text=True, encoding="utf-8")
            return json.loads(raw)
        except Exception:
            pass
    with httpx.Client(timeout=40.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


def find_gh() -> Path | None:
    path = shutil.which("gh")
    if path:
        return Path(path)
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "gh.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GitHub CLI" / "gh.exe",
        Path(os.environ.get("ProgramFiles", "")) / "GitHub CLI" / "gh.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "GitHub CLI" / "gh.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def choose_mihomo_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        candidates = ["windows-amd64-compatible", "windows-amd64-v1", "windows-amd64"]
        suffix = ".zip"
    elif system == "linux":
        if "arm64" in machine or "aarch64" in machine:
            candidates = ["linux-arm64"]
        else:
            candidates = ["linux-amd64-compatible", "linux-amd64-v1", "linux-amd64"]
        suffix = ".gz"
    elif system == "darwin":
        candidates = ["darwin-arm64"] if "arm" in machine else ["darwin-amd64-compatible", "darwin-amd64"]
        suffix = ".gz"
    else:
        return None

    for key in candidates:
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if key in name and name.endswith(suffix):
                return asset
    return None


def download_file(url: str, path: Path) -> None:
    with httpx.stream("GET", url, timeout=120.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as resp:
        resp.raise_for_status()
        with path.open("wb") as fh:
            for chunk in resp.iter_bytes():
                if chunk:
                    fh.write(chunk)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_with_mihomo(
    mihomo: Path,
    runtime: Path,
    candidates: list[Candidate],
    rounds: int,
    timeout_ms: int,
    workers: int,
    probe_urls: list[str],
) -> list[TestResult]:
    controller_port = free_port()
    mixed_port = free_port()
    config_path = runtime / "mihomo-test.yaml"
    controller = f"127.0.0.1:{controller_port}"
    write_mihomo_test_config(config_path, candidates, mixed_port, controller)

    log_path = runtime / "mihomo.log"
    log_fh = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(mihomo), "-d", str(runtime), "-f", str(config_path)],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        wait_for_mihomo(controller_port, proc)
        return run_delay_tests(controller_port, candidates, rounds, timeout_ms, workers, probe_urls)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=8)
        log_fh.close()


def write_mihomo_test_config(path: Path, candidates: list[Candidate], mixed_port: int, controller: str) -> None:
    names = [c.proxy["name"] for c in candidates]
    config = {
        "mixed-port": mixed_port,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "warning",
        "external-controller": controller,
        "secret": "",
        "ipv6": False,
        "dns": {
            "enable": True,
            "ipv6": False,
            "enhanced-mode": "fake-ip",
            "nameserver": ["https://1.1.1.1/dns-query", "https://dns.google/dns-query"],
            "fallback": ["tls://8.8.8.8", "tls://1.0.0.1"],
        },
        "proxies": [c.proxy for c in candidates],
        "proxy-groups": [{"name": "PROXY", "type": "select", "proxies": names}],
        "rules": ["MATCH,PROXY"],
    }
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")


def wait_for_mihomo(controller_port: int, proc: subprocess.Popen[Any]) -> None:
    url = f"http://127.0.0.1:{controller_port}/version"
    deadline = time.time() + 25
    last_error = "not started"
    with httpx.Client(timeout=2.0) as client:
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"mihomo exited early with code {proc.returncode}")
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    return
                last_error = f"HTTP {resp.status_code}"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"mihomo controller did not start: {last_error}")


def run_delay_tests(
    controller_port: int,
    candidates: list[Candidate],
    rounds: int,
    timeout_ms: int,
    workers: int,
    probe_urls: list[str],
) -> list[TestResult]:
    base = f"http://127.0.0.1:{controller_port}"

    def test_one(candidate: Candidate) -> TestResult:
        delays: list[int] = []
        errors: list[str] = []
        sequence = []
        for i in range(rounds):
            sequence.append(probe_urls[i % len(probe_urls)])
        random.shuffle(sequence)

        with httpx.Client(timeout=(timeout_ms / 1000.0) + 3.0) as client:
            for probe_url in sequence:
                encoded_name = urllib.parse.quote(candidate.proxy["name"], safe="")
                encoded_probe = urllib.parse.quote(probe_url, safe="")
                url = f"{base}/proxies/{encoded_name}/delay?timeout={timeout_ms}&url={encoded_probe}"
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        errors.append(f"HTTP {resp.status_code}")
                        continue
                    data = resp.json()
                    delay = data.get("delay")
                    if isinstance(delay, (int, float)) and delay > 0:
                        delays.append(int(delay))
                    else:
                        errors.append(str(data.get("message") or data))
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))

        avg = sum(delays) / len(delays) if delays else None
        mn = min(delays) if delays else None
        mx = max(delays) if delays else None
        jitter = (mx - mn) if len(delays) >= 2 and mx is not None and mn is not None else None
        score = final_score(candidate, avg, jitter, len(delays), rounds)
        return TestResult(
            name=candidate.proxy["name"],
            source=candidate.source,
            proxy_type=str(candidate.proxy.get("type", "")),
            avg_delay=avg,
            min_delay=mn,
            max_delay=mx,
            jitter=jitter,
            success_count=len(delays),
            total_count=rounds,
            score=score,
            error="; ".join(errors[:3]) if errors and not delays else None,
            proxy=candidate.proxy,
        )

    results: list[TestResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(test_one, c) for c in candidates]
        for idx, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            if idx % 25 == 0 or idx == len(candidates):
                ok = sum(1 for r in results if r.success_count > 0)
                print(f"  tested {idx}/{len(candidates)}; alive {ok}", flush=True)
    return results


def final_score(candidate: Candidate, avg: float | None, jitter: float | None, success_count: int, rounds: int) -> float:
    if not avg:
        return -100000 + candidate.pre_score * 0.01
    success_rate = success_count / max(1, rounds)
    stability_bonus = success_rate * 900
    jitter_penalty = (jitter or 0) * 0.35
    delay_penalty = avg * 0.55
    clean_bonus = candidate.pre_score * 0.18
    return clean_bonus + stability_bonus - delay_penalty - jitter_penalty


def select_winners(
    results: list[TestResult],
    top: int,
    max_delay_ms: int,
    max_jitter_ms: int,
    min_success_rate: float,
) -> list[TestResult]:
    viable = [
        r
        for r in results
        if r.success_count >= max(1, math.ceil(r.total_count * min_success_rate))
        and r.avg_delay is not None
        and r.avg_delay <= max_delay_ms
        and (r.jitter is None or r.jitter <= max_jitter_ms)
    ]
    viable.sort(key=lambda r: (r.score, r.success_rate, -(r.avg_delay or 99999)), reverse=True)
    return viable[:top]


def emit_outputs(
    out: Path,
    winners: list[TestResult],
    all_results: list[TestResult],
    sources: list[Source],
    args: argparse.Namespace,
) -> None:
    generated = time.strftime("%Y-%m-%d %H:%M:%S %z")
    proxies = [r.proxy for r in winners]
    names = [p["name"] for p in proxies]
    quality_config = build_quality_config(proxies, names)

    (out / "quality.yaml").write_text(
        "# Generated by Quality Node Forge\n"
        f"# Generated at: {generated}\n"
        + yaml.safe_dump(quality_config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (out / "quality-provider.yaml").write_text(
        yaml.safe_dump({"proxies": proxies}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (out / "tested.json").write_text(
        json.dumps([result_to_dict(r) for r in sorted(all_results, key=lambda x: x.score, reverse=True)], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "report.md").write_text(build_report(winners, all_results, sources, args, generated), encoding="utf-8")


def build_quality_config(proxies: list[dict[str, Any]], names: list[str]) -> dict[str, Any]:
    if not names:
        names = ["DIRECT"]
    groups = [
        {
            "name": "Proxy",
            "type": "select",
            "proxies": ["Auto", "Fallback", *names, "DIRECT"],
        },
        {
            "name": "Auto",
            "type": "url-test",
            "proxies": names,
            "url": "https://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 50,
        },
        {
            "name": "Fallback",
            "type": "fallback",
            "proxies": names,
            "url": "https://www.gstatic.com/generate_204",
            "interval": 180,
        },
    ]
    return {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "ipv6": False,
        "proxies": proxies,
        "proxy-groups": groups,
        "rules": ["MATCH,Proxy"],
    }


def result_to_dict(r: TestResult) -> dict[str, Any]:
    return {
        "name": r.name,
        "source": r.source,
        "type": r.proxy_type,
        "avg_delay": r.avg_delay,
        "min_delay": r.min_delay,
        "max_delay": r.max_delay,
        "jitter": r.jitter,
        "success_count": r.success_count,
        "total_count": r.total_count,
        "success_rate": r.success_rate,
        "score": r.score,
        "error": r.error,
    }


def build_report(
    winners: list[TestResult],
    all_results: list[TestResult],
    sources: list[Source],
    args: argparse.Namespace,
    generated: str,
) -> str:
    alive = [r for r in all_results if r.success_count > 0]
    lines = [
        "# Quality Node Forge Report",
        "",
        f"- Generated at: `{generated}`",
        f"- Sources: `{len(sources)}`",
        f"- Tested candidates: `{len(all_results)}`",
        f"- Alive candidates: `{len(alive)}`",
        f"- Winners: `{len(winners)}`",
        f"- Max delay threshold: `{args.max_delay_ms} ms`",
        f"- Max jitter threshold: `{args.max_jitter_ms} ms`",
        f"- Min success rate: `{args.min_success_rate:.2f}`",
        "",
        "## Winners",
        "",
        "| # | Name | Type | Source | Success | Avg | Jitter | Score |",
        "|---:|---|---|---|---:|---:|---:|---:|",
    ]
    for idx, r in enumerate(winners, start=1):
        lines.append(
            "| {idx} | {name} | {typ} | {src} | {ok}/{total} | {avg} | {jitter} | {score:.1f} |".format(
                idx=idx,
                name=escape_md(r.name),
                typ=escape_md(r.proxy_type),
                src=escape_md(r.source),
                ok=r.success_count,
                total=r.total_count,
                avg=f"{r.avg_delay:.0f} ms" if r.avg_delay is not None else "-",
                jitter=f"{r.jitter:.0f} ms" if r.jitter is not None else "-",
                score=r.score,
            )
        )
    lines.extend(
        [
            "",
            "## Sources",
            "",
            "| Source | Weight | Notes |",
            "|---|---:|---|",
        ]
    )
    for s in sources:
        lines.append(f"| {escape_md(s.name)} | {s.weight:.2f} | {escape_md(s.notes)} |")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Public free nodes cannot guarantee privacy or long-term stability.",
            "- `quality.yaml` can be imported directly into Clash Verge / FlClash.",
            "- If winners are few, the current public pool is weak; this tool prefers quality over count.",
        ]
    )
    return "\n".join(lines) + "\n"


def escape_md(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
