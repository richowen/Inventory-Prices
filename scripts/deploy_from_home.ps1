param(
    [string]$PiHost    = "farmprices.west-stonecat.ts.net",
    [string]$PiUser    = "richowen",
    [string]$Branch    = "main",
    [string]$RepoDir   = "/home/richowen/Inventory-Prices",
    [string]$AppDir    = "/home/richowen/Inventory-Prices/farmprices",
    [string]$ServiceName = "farmprices",
    [string]$RepoUrl   = "https://github.com/YOUR_USERNAME/YOUR_REPO.git"
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

# Build the remote command:
# 1. If the repo isn't cloned yet, clone it first (so the deploy script exists).
# 2. Then hand off to the deploy script which handles everything else.
$remoteCmd = @"
set -e
if [ ! -d '$RepoDir/.git' ]; then
  echo '[remote] Repo not found — cloning $RepoUrl'
  git clone --branch '$Branch' '$RepoUrl' '$RepoDir'
  echo '[remote] Clone complete'
fi
REPO_DIR='$RepoDir' APP_DIR='$AppDir' BRANCH='$Branch' SERVICE_NAME='$ServiceName' REPO_URL='$RepoUrl' bash '$RepoDir/farmprices/deploy/remote_deploy.sh'
"@

Write-Step "Running remote deploy on $PiUser@$PiHost"
ssh "$PiUser@$PiHost" "bash -lc $(([char]39) + $remoteCmd + ([char]39))"
if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed."
}

Write-Step "Deployment completed successfully"
