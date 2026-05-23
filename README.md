# Quality Node Forge

这是一个给 Clash Verge / FlClash 使用的“精品节点筛选器”。

它不追求节点数量，而是按下面的流程生成少量高质量订阅：

1. 只抓取少数高质量公开上游。
2. 解析 Clash/Mihomo 格式节点。
3. 去掉重复、明显广告、订阅说明、流量提示类节点。
4. 下载并启动 Mihomo 内核。
5. 通过 Mihomo 的真实代理延迟接口逐个检测节点。
6. 按可用次数、延迟、稳定性、协议安全性和上游可信度评分。
7. 输出 Clash Verge / FlClash 可直接导入的 `quality.yaml`。

## 快速运行

```powershell
cd D:\OneDrive\Desktop\codex闲聊\quality-node-forge
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m quality_node_forge run --top 30
```

默认规则偏严格：

- 每个入选节点必须多轮检测全部成功。
- 平均延迟默认不超过 `1800 ms`。
- 抖动默认不超过 `700 ms`。
- 节点名会被重写成纯净格式，避免广告词、表情或乱码影响导入。

运行完成后看：

- `outputs/quality.yaml`：Clash Verge / FlClash 导入用。
- `outputs/quality-provider.yaml`：只包含节点列表，适合做 provider。
- `outputs/report.md`：本次筛选报告。
- `outputs/tested.json`：详细检测数据。

## GitHub 自动订阅

部署到 GitHub 后，工作流会每 3 小时自动运行一次，也可以在 GitHub Actions 页面手动点 `Run workflow`。

Clash Verge / FlClash 订阅地址：

```text
https://raw.githubusercontent.com/wenma77/quality-node-forge/main/outputs/quality.yaml
```

备用 CDN 地址：

```text
https://cdn.jsdelivr.net/gh/wenma77/quality-node-forge@main/outputs/quality.yaml
```

如果节点不好用了，在客户端里更新订阅即可；如果想立刻刷新源头数据，就去 GitHub Actions 手动运行一次 `Update quality subscription`。

## 重要说明

免费公开节点无法保证长期稳定，也无法保证隐私安全。这个工具只能提高“真实可用、低延迟、少量优选”的概率，不能把公开免费节点变成可信专线。

如果要更“干净”，建议只访问普通网页，不要在免费节点里登录重要账号、传输隐私文件或处理支付/银行类信息。
