#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys
import time
from typing import Any

import aiohttp
from aiohttp import web

LOG = logging.getLogger("shelly-proxy")


def transform_em_getstatus(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)

    if out.get("n_current") is None:
        out["n_current"] = 0.0

    out.pop("user_calibrated_phase", None)

    for phase_key in ("total_current", "total_act_power", "total_aprt_power"):
        if phase_key not in out or out[phase_key] is None:
            part_key = phase_key.replace("total_", "")
            try:
                out[phase_key] = round(
                    (out.get(f"a_{part_key}") or 0)
                    + (out.get(f"b_{part_key}") or 0)
                    + (out.get(f"c_{part_key}") or 0),
                    3,
                )
            except (TypeError, ValueError):
                out[phase_key] = 0.0

    return out


def transform_em_getstatus_after_parse(body_text: str) -> str:
    import json

    try:
        parsed = json.loads(body_text)
    except json.JSONDecodeError:
        return body_text
    if not isinstance(parsed, dict):
        return body_text
    new = transform_em_getstatus(parsed)
    return json.dumps(new, separators=(",", ":"))


class ShellyProxy:
    def __init__(
        self, upstream_host: str, upstream_port: int = 80, timeout: float = 5.0
    ):
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def startup(self, app: web.Application) -> None:
        self._session = aiohttp.ClientSession(timeout=self.timeout)

    async def cleanup(self, app: web.Application) -> None:
        if self._session is not None:
            await self._session.close()

    @property
    def upstream_base(self) -> str:
        return f"http://{self.upstream_host}:{self.upstream_port}"

    async def handle(self, request: web.Request) -> web.StreamResponse:
        assert self._session is not None

        target_url = f"{self.upstream_base}{request.rel_url}"
        method = request.method

        body = await request.read() if request.can_read_body else None

        hdrs = {
            k: v
            for k, v in request.headers.items()
            if k.lower()
            not in ("host", "content-length", "connection", "transfer-encoding")
        }
        hdrs["Host"] = self.upstream_host

        start = time.monotonic()
        try:
            async with self._session.request(
                method,
                target_url,
                headers=hdrs,
                data=body,
                allow_redirects=False,
            ) as upstream:
                raw = await upstream.read()
                status = upstream.status
                content_type = upstream.headers.get(
                    "Content-Type", "application/octet-stream"
                )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            LOG.warning("Upstream error for %s: %s", target_url, exc)
            return web.Response(status=502, text=f"Upstream error: {exc}")

        elapsed_ms = (time.monotonic() - start) * 1000.0

        path = request.rel_url.path
        if (
            path == "/rpc/EM.GetStatus"
            and status == 200
            and content_type.startswith("application/json")
        ):
            try:
                new_text = transform_em_getstatus_after_parse(raw.decode("utf-8"))
                LOG.info("EM.GetStatus transformed (%.1f ms)", elapsed_ms)
                return web.Response(
                    status=200,
                    body=new_text.encode("utf-8"),
                    content_type="application/json",
                    headers={"Server": "ShellyHTTP/1.0.0"},
                )
            except Exception as exc:  # pragma: no cover
                LOG.exception("Transform failed, passing through: %s", exc)

        LOG.debug("Passthrough %s %s -> %d (%.1f ms)", method, path, status, elapsed_ms)
        resp = web.Response(status=status, body=raw)
        resp.headers["Content-Type"] = content_type
        return resp


def build_app(
    upstream_host: str, upstream_port: int, timeout: float
) -> web.Application:
    app = web.Application()
    proxy = ShellyProxy(upstream_host, upstream_port, timeout)
    app.on_startup.append(proxy.startup)
    app.on_cleanup.append(proxy.cleanup)

    app.router.add_route("*", "/{tail:.*}", proxy.handle)
    return app


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Shelly 3EM-63W Gen3 -> Pro 3EM API Proxy",
    )
    parser.add_argument(
        "--shelly",
        required=True,
        help="IP / hostname of the real Gen3 device",
    )
    parser.add_argument(
        "--shelly-port",
        type=int,
        default=80,
        help="Upstream port (default: 80)",
    )
    parser.add_argument(
        "--bind",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument("--port", type=int, default=80, help="Proxy port (default: 80)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Upstream timeout in seconds (default: 5)",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase logging (-v, -vv)"
    )
    args = parser.parse_args()

    level = logging.WARNING - 10 * args.verbose
    logging.basicConfig(
        level=max(level, logging.DEBUG),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = build_app(args.shelly, args.shelly_port, args.timeout)
    LOG.warning(
        "Proxy starts: http://%s:%d -> %s:%d",
        args.bind,
        args.port,
        args.shelly,
        args.shelly_port,
    )
    web.run_app(app, host=args.bind, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
