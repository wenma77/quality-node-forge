# Quality Node Forge Report

- Generated at: `2026-05-23 22:38:01 +0800`
- Sources: `10`
- Tested candidates: `717`
- Alive candidates: `31`
- Winners: `7`
- Max delay threshold: `1800 ms`
- Max jitter threshold: `700 ms`
- Min success rate: `1.00`

## Winners

| # | Name | Type | Source | Success | Avg | Jitter | Score |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | 373-AVF-VMESS-82.198.246.9-180 | vmess | Au1rxx verified feed | 3/3 | 730 ms | 12 ms | 726.5 |
| 2 | 161-VVS-VLESS-64.186.232.95-443 | vless | VovaplusEXP VLESS secure | 3/3 | 1040 ms | 268 ms | 483.3 |
| 3 | 139-VVS-VLESS-64.186.225.13-8443 | vless | VovaplusEXP VLESS secure | 3/3 | 1029 ms | 322 ms | 470.8 |
| 4 | 543-VE-SS-185.189.160.105-41632 | ss | V2RayAggregator eternity | 3/3 | 806 ms | 679 ms | 382.7 |
| 5 | 183-VVS-VLESS-64.186.227.227-443 | vless | VovaplusEXP VLESS secure | 3/3 | 1188 ms | 370 ms | 366.4 |
| 6 | 463-PBF-VLESS-217.145.226.147-2083 | vless | Pawdroid base64 feed | 3/3 | 1323 ms | 138 ms | 299.4 |
| 7 | 242-VVS-VLESS-154.17.5.177-443 | vless | VovaplusEXP VLESS secure | 3/3 | 1248 ms | 666 ms | 230.0 |

## Sources

| Source | Weight | Notes |
|---|---:|---|
| Au1rxx verified feed | 1.35 | Hourly feed, sing-box real HTTP verification before publishing. |
| VovaplusEXP VLESS secure | 1.18 | Speed-tested Clash Meta profile, secure VLESS set. |
| VovaplusEXP Trojan | 1.12 | Speed-tested Clash Meta profile, Trojan set. |
| VovaplusEXP Shadowsocks | 1.03 | Speed-tested Clash Meta profile, SS set. |
| awesome-vpn clash | 0.88 | Broad fallback source, lower trust than verified feeds. |
| V2RayAggregator eternity | 0.82 | Large fallback source filtered by speed upstream. |
| Pawdroid base64 feed | 0.68 | Large public base64 feed; used only as a fallback and filtered strictly. |
| freefq base64 feed | 0.62 | Public base64 feed; useful for extra candidates after real testing. |
| xiaoji clashnodecc | 0.58 | Public Clash feed; low trust, strict real testing required. |
| xiaoji v2rayshare | 0.58 | Public Clash feed; low trust, strict real testing required. |

## Notes

- Public free nodes cannot guarantee privacy or long-term stability.
- `quality.yaml` can be imported directly into Clash Verge / FlClash.
- If winners are few, the current public pool is weak; this tool prefers quality over count.
