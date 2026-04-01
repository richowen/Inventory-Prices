param(
    [string]$PiHost = "farmprices.west-stonecat.ts.net",
    [string]$PiUser = "richowen",
    [string]$Branch = "main",
    [string]$RepoDir = "/home/richowen/Inventory-Prices",
    [string]$AppDir = "/home/richowen/Inventory-Prices/farmprices",
    [string]$ServiceName = "farmprices"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[deploy] $Message"
}

Write-Step "Starting deploy trigger (SSH only; no local git push)"

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "ssh is not installed or not available in PATH."
}

$remoteCmd = "echo '[remote] starting deploy'; REPO_DIR='$RepoDir' APP_DIR='$AppDir' BRANCH='$Branch' SERVICE_NAME='$ServiceName' bash '$AppDir/deploy/remote_deploy.sh'"

Write-Step "Running remote deploy on $PiUser@$PiHost"
ssh "$PiUser@$PiHost" "bash -lc $([char]34)$remoteCmd$([char]34)"
if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed."
}

Write-Step "Deployment completed successfully"
