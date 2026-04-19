# shelly-proxy

A small transparent HTTP proxy that makes a **Shelly 3EM-63W / 3EM-63T
Gen3** look like a **Shelly Pro 3EM** to inverters and energy management
systems that only support the older model.

Built specifically for the case where a **Solakon ONE** (based on Growatt
NOAH) or similar inverter lists a Gen3 3EM device as "found" but never
acts on its readings. Should also help with any other integration that
expects the Pro 3EM response shape.

## What it does

The Gen3 and Pro 3EM APIs are almost identical. Only two things trip up
strict clients:

| Field | Pro 3EM | 3EM-63W Gen3 | Proxy rewrites to |
|-------|---------|--------------|-------------------|
| `n_current` | number (e.g. `0.02`) | `null` (no N clamp) | `0.0` |
| `user_calibrated_phase` | absent | empty array | removed |

Everything else is passed through unchanged. All other endpoints (`/rpc/Shelly.GetStatus`, etc.) are proxied.

## Usage

You have to run the proxy on some device in your network which is reachable by your inverter.
The proxy has to be able to reach the Shelly.
Point your inverter to the shelly-proxy IP instead of the real device.

## Note on AI usage

The protocol differences between the Gen3 and Pro 3EM were identified by analyzing a packet capture using AI, which also generated the initial implementation.
Code has been reviewed and tested before publication.

## Requirements

- Python 3.10+
- `aiohttp`

```sh
pip install aiohttp
```

## Usage

```sh
python3 shelly_proxy.py --shelly <gen3-ip> --port 80 --bind 0.0.0.0
```

| Flag | Description | Default |
|------|-------------|---------|
| `--shelly` | IP / hostname of the real Gen3 device | required |
| `--shelly-port` | Upstream port | `80` |
| `--bind` | Bind address | `0.0.0.0` |
| `--port` | Proxy port | `80` |
| `--timeout` | Upstream timeout in seconds | `5.0` |
| `-v` / `-vv` | Increase logging (info / debug) | warning |

## Verify it works

While the proxy is running:

```sh
curl -s http://<proxy-ip>/rpc/EM.GetStatus?id=0 | python3 -m json.tool
```

You should see `"n_current": 0.0` (not `null`) and no
`user_calibrated_phase` field. All other values are live from the Gen3.

## License

MIT
