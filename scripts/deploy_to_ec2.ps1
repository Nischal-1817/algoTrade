# Deploy algoTrade live trading to EC2 (from Windows PowerShell).

param(
    [string]$Ec2Host = "<EC2_PUBLIC_IP>",
    [string]$User = "ec2-user",
    [string]$Key = $(if (Test-Path "$env:USERPROFILE\.ssh\algoTrade_ec2") { "$env:USERPROFILE\.ssh\algoTrade_ec2" } else { "$PSScriptRoot\..\shonya_key_pair.pem" })
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\.."

$includes = @(
    "algo_trade",
    "scripts",
    "dashboard",
    "deploy",
    "data/watchlist.json",
    "requirements.txt",
    "credentials.py",
    "USAGE.txt"
)

$tar = Join-Path $env:TEMP "algoTrade_deploy.tar.gz"
if (Test-Path $tar) { Remove-Item $tar -Force }

Push-Location $Root
try {
    & tar -czf $tar @includes
} finally {
    Pop-Location
}

$remote = "${User}@${Ec2Host}"
Write-Host "Uploading to $remote ..."
& scp -i $Key $tar "${remote}:~/algoTrade_deploy.tar.gz"
& scp -i $Key "$Root\deploy\ec2\remote_setup.sh" "${remote}:~/remote_setup.sh"

Write-Host "Running remote setup ..."
& ssh -i $Key $remote "sed -i 's/\r$//' ~/remote_setup.sh && chmod +x ~/remote_setup.sh && bash ~/remote_setup.sh"

Write-Host "Done. Tail logs: ssh -i $Key $remote 'tail -f ~/algoTrade/logs/live_service.log'"
