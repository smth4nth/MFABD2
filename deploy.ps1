param(
    [switch]$All,     # 同时上传 APK 文件
    [switch]$Restart  # 上传后重启 Docker 容器
)

$PEM    = "$PSScriptRoot\tencent-sg.pem"
$SERVER = "ubuntu@43.160.196.56"
$REMOTE = "~/bd2-deploy"
$SCP    = "scp -i `"$PEM`" -o StrictHostKeyChecking=no"
$SSH    = "ssh -i `"$PEM`" -o StrictHostKeyChecking=no $SERVER"

# 修复 PEM 权限（Windows 上 SSH 要求密钥权限严格）
$acl = Get-Acl $PEM
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME, "Read", "Allow")
$acl.SetAccessRule($rule)
Set-Acl $PEM $acl

function Upload($local, $remote) {
    Write-Host "  -> $local" -ForegroundColor Gray
    Invoke-Expression "$SCP `"$local`" `"${SERVER}:${remote}`""
    if (-not $?) { Write-Host "  [失败]" -ForegroundColor Red; exit 1 }
}

Write-Host ""
Write-Host "=== 部署到腾讯云 (43.160.196.56) ===" -ForegroundColor Cyan

Write-Host ""
Write-Host "[1] 上传配置文件" -ForegroundColor Yellow
Upload "$PSScriptRoot\deploy\docker-compose.yml" "$REMOTE/docker-compose.yml"
Upload "$PSScriptRoot\deploy\setup.sh"           "$REMOTE/setup.sh"

if ($All) {
    Write-Host ""
    Write-Host "[2] 上传 APK 文件" -ForegroundColor Yellow
    Get-ChildItem "$PSScriptRoot\deploy\apk\*" | ForEach-Object {
        Upload $_.FullName "$REMOTE/$($_.Name)"
    }
}

if ($Restart) {
    Write-Host ""
    Write-Host "[3] 重启 Docker 容器" -ForegroundColor Yellow
    Invoke-Expression "$SSH `"cd $REMOTE && sudo docker compose up -d`""
    if ($?) {
        Write-Host "  容器已重启" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "=== 完成 ===" -ForegroundColor Green
Write-Host ""
