# 高质量节点订阅工具

这是给 Clash Verge / FlClash 使用的手动更新订阅项目。它会在你的本机网络环境下抓取公开节点源，清洗重复和广告节点，给节点补上国家/地区名称，再输出可以直接导入客户端的订阅文件。

## 订阅地址

主订阅，推荐使用：

```text
https://raw.githubusercontent.com/wenma77/quality-node-forge/main/outputs/quality.yaml
```

备用 CDN 地址：

```text
https://cdn.jsdelivr.net/gh/wenma77/quality-node-forge@main/outputs/quality.yaml
```

严格版副本：

```text
https://raw.githubusercontent.com/wenma77/quality-node-forge/main/outputs/strict.yaml
```

## 现在的筛选逻辑

`quality.yaml` 是主订阅。现在它最多保留 12 个严格入选节点：3 轮测速全部成功、平均延迟不高于 1800ms、抖动不高于 800ms。不会再为了凑数量补入“可能可用”的候选节点。

`strict.yaml` 保留为严格版副本，方便以后对比或单独引用。GitHub 服务器的网络环境和你本地不同，所以它测通不代表你本地一定能用，但这种策略会明显减少订阅里一大片 Timeout 的情况。

节点名称会尽量写成这种格式：

```text
001-美国-US-VLESS-64.186.232.95-443
002-日本-JP-TROJAN-example.com-443
```

这样在 Clash Verge / FlClash 里能直接看到国家或地区。

## 更新方式

主订阅应该尽量用你的本机网络测试后再发布。GitHub 服务器在国外，它测出来快的节点，在你本地可能全部 Timeout。

所以当前仓库不再让 GitHub Actions 每小时自动覆盖 `quality.yaml`。需要刷新时，应在本机运行一次严格测速，再把结果发布到同一个订阅链接。若本机严格合格节点少于 2 个，本次更新会失败并保留上一版。

## 输出文件

- `outputs/quality.yaml`：主订阅，推荐导入 Clash Verge / FlClash。
- `outputs/quality-provider.yaml`：主订阅的节点 provider 文件。
- `outputs/strict.yaml`：严格版副本。
- `outputs/strict-provider.yaml`：严格版节点 provider 文件。
- `outputs/report.md`：中文报告，能看本次抓取、测试和输出情况。
- `outputs/tested.json`：完整测试数据，方便后续排查。

## 本地运行

```powershell
cd D:\OneDrive\Desktop\codex闲聊\quality-node-forge
.\.venv\Scripts\python.exe -m quality_node_forge run --candidate-limit 3000 --output-limit 12 --top 12 --rounds 3 --workers 32 --timeout-ms 3000 --max-delay-ms 1800 --max-jitter-ms 800 --min-success-rate 1.0 --min-winners 2
```

## 双击手动更新

在项目目录里双击：

```text
一键本机测速并更新订阅.cmd
```

它会用本机网络测速，至少筛出 2 个严格合格节点才上传到 GitHub。若本轮质量不够，会停止并保留上一版订阅。

## 重要说明

免费公开节点无法保证长期稳定，也无法保证隐私安全。这个工具只能提高“更可能可用、节点名清楚、更新及时”的概率，不能把免费公开节点变成可信专线。

建议只用于普通网页访问，不要用免费节点登录重要账号、传输隐私文件，或处理支付、银行等敏感信息。
