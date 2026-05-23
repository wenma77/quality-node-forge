# 高质量节点订阅工具

这是给 Clash Verge / FlClash 使用的自动订阅项目。它会定时抓取公开节点源，清洗重复和广告节点，给节点补上国家/地区名称，再输出可以直接导入客户端的订阅文件。

## 订阅地址

主订阅，推荐使用：

```text
https://raw.githubusercontent.com/wenma77/quality-node-forge/main/outputs/quality.yaml
```

备用 CDN 地址：

```text
https://cdn.jsdelivr.net/gh/wenma77/quality-node-forge@main/outputs/quality.yaml
```

严格云端测速版：

```text
https://raw.githubusercontent.com/wenma77/quality-node-forge/main/outputs/strict.yaml
```

## 现在的筛选逻辑

`quality.yaml` 是主订阅。它不是只保留 GitHub 云端测通的极少数节点，而是保留一个小而干净的候选池，让 Clash Verge / FlClash 在你的电脑或手机本地继续测速。这样比“GitHub 测通就算好”更适合你实际使用。

`strict.yaml` 是 GitHub 云端严格测通的节点。它可以作为参考，但 GitHub 服务器的网络环境和你本地不同，所以它测通不代表你本地一定能用。

节点名称会尽量写成这种格式：

```text
001-美国-US-VLESS-64.186.232.95-443
002-日本-JP-TROJAN-example.com-443
```

这样在 Clash Verge / FlClash 里能直接看到国家或地区。

## 自动更新

GitHub Actions 每小时自动运行一次。你在 Clash Verge / FlClash 里更新订阅后，就会拿到最新生成的节点列表。

如果想立刻刷新，可以在 GitHub 仓库的 Actions 页面手动运行“更新高质量订阅”。

## 输出文件

- `outputs/quality.yaml`：主订阅，推荐导入 Clash Verge / FlClash。
- `outputs/quality-provider.yaml`：主订阅的节点 provider 文件。
- `outputs/strict.yaml`：GitHub 云端严格测通版。
- `outputs/strict-provider.yaml`：严格版节点 provider 文件。
- `outputs/report.md`：中文报告，能看本次抓取、测试和输出情况。
- `outputs/tested.json`：完整测试数据，方便后续排查。

## 本地运行

```powershell
cd D:\OneDrive\Desktop\codex闲聊\quality-node-forge
.\.venv\Scripts\python.exe -m quality_node_forge run --candidate-limit 360 --output-limit 80 --top 30
```

## 重要说明

免费公开节点无法保证长期稳定，也无法保证隐私安全。这个工具只能提高“更可能可用、节点名清楚、更新及时”的概率，不能把免费公开节点变成可信专线。

建议只用于普通网页访问，不要用免费节点登录重要账号、传输隐私文件，或处理支付、银行等敏感信息。
