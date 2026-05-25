$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Repo = "wenma77/quality-node-forge"
$SubscriptionUrl = "https://raw.githubusercontent.com/wenma77/quality-node-forge/main/outputs/quality.yaml"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Mihomo = Join-Path $ProjectRoot "tools\mihomo\mihomo.exe"

function Write-Step($Text) {
    Write-Host ""
    Write-Host "== $Text ==" -ForegroundColor Cyan
}

function Invoke-Checked($FilePath, [string[]]$Arguments, $FailureMessage) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage，退出码：$LASTEXITCODE"
    }
}

function Find-GitHubCli {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\gh.exe",
        "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe",
        "$env:ProgramFiles\GitHub CLI\gh.exe",
        "${env:ProgramFiles(x86)}\GitHub CLI\gh.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    throw "没有找到 GitHub CLI。请先安装并登录 gh。"
}

function Publish-Outputs($Gh) {
    $files = @(
        "outputs/quality.yaml",
        "outputs/quality-provider.yaml",
        "outputs/strict.yaml",
        "outputs/strict-provider.yaml",
        "outputs/report.md",
        "outputs/tested.json"
    )

    $base = & $Gh api "repos/$Repo/git/ref/heads/main" --jq ".object.sha"
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($base)) {
        throw "读取 GitHub main 分支失败。"
    }

    $tree = @()
    foreach ($file in $files) {
        $resolved = Resolve-Path -LiteralPath $file
        $bytes = [System.IO.File]::ReadAllBytes($resolved)
        $blobBody = @{
            content = [Convert]::ToBase64String($bytes)
            encoding = "base64"
        } | ConvertTo-Json -Compress

        $blob = ($blobBody | & $Gh api -X POST "repos/$Repo/git/blobs" --input -) | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($blob.sha)) {
            throw "上传文件失败：$file"
        }

        $tree += @{
            path = $file
            mode = "100644"
            type = "blob"
            sha = $blob.sha
        }
        Write-Host "已准备上传：$file"
    }

    $treeBody = @{
        base_tree = $base
        tree = $tree
    } | ConvertTo-Json -Depth 10 -Compress
    $treeObj = ($treeBody | & $Gh api -X POST "repos/$Repo/git/trees" --input -) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($treeObj.sha)) {
        throw "创建 GitHub 文件树失败。"
    }

    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $commitBody = @{
        message = "chore: update local tested subscription $now"
        tree = $treeObj.sha
        parents = @($base)
    } | ConvertTo-Json -Depth 10 -Compress
    $commitObj = ($commitBody | & $Gh api -X POST "repos/$Repo/git/commits" --input -) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($commitObj.sha)) {
        throw "创建 GitHub 提交失败。"
    }

    $refBody = @{
        sha = $commitObj.sha
        force = $false
    } | ConvertTo-Json -Compress
    $null = $refBody | & $Gh api -X PATCH "repos/$Repo/git/refs/heads/main" --input -
    if ($LASTEXITCODE -ne 0) {
        throw "更新 GitHub main 分支失败。"
    }

    return $commitObj.sha
}

try {
    Write-Host "本机高质量节点测速更新"
    Write-Host "项目目录：$ProjectRoot"

    if (-not (Test-Path -LiteralPath $Python)) {
        throw "找不到 Python 环境：$Python"
    }

    Write-Step "开始本机严格测速"
    $runArgs = @(
        "-m", "quality_node_forge", "run",
        "--candidate-limit", "3000",
        "--output-limit", "12",
        "--top", "12",
        "--rounds", "3",
        "--workers", "32",
        "--timeout-ms", "3000",
        "--max-delay-ms", "1800",
        "--max-jitter-ms", "800",
        "--min-success-rate", "1.0",
        "--min-winners", "2"
    )
    Invoke-Checked $Python $runArgs "本轮测速没有达到发布标准，订阅没有上传"

    Write-Step "校验 Clash/Mihomo 配置"
    Invoke-Checked $Mihomo @("-t", "-d", "runtime", "-f", "outputs\quality.yaml") "主订阅配置校验失败"
    Invoke-Checked $Mihomo @("-t", "-d", "runtime", "-f", "outputs\strict.yaml") "严格订阅配置校验失败"

    Write-Step "上传到 GitHub 订阅链接"
    $Gh = Find-GitHubCli
    & $Gh auth status
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI 未登录，请先运行 gh auth login。"
    }
    $commit = Publish-Outputs $Gh

    Write-Step "完成"
    $report = Get-Content -LiteralPath "outputs\report.md" -Encoding UTF8
    $report | Select-String -Pattern "主订阅输出|严格优选|延迟阈值|抖动阈值" | ForEach-Object {
        Write-Host $_.Line
    }
    Write-Host ""
    Write-Host "GitHub 提交：$commit"
    Write-Host "订阅链接：$SubscriptionUrl"
    Write-Host ""
    Write-Host "现在可以去 Clash Verge / FlClash 里更新订阅。"
}
catch {
    Write-Host ""
    Write-Host "失败：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "订阅没有被上传或覆盖。上一版会继续保留。"
    exit 1
}
