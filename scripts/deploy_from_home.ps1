param(
    [string]$PiHost    = "farmprices.west-stonecat.ts.net",
    [string]$PiUser    = "richowen",
    [string]$Branch    = "main",
    [string]$RepoDir   = "/home/richowen/Inventory-Prices",
    [string]$AppDir    = "/home/richowen/Inventory-Prices/farmprices",
    [string]$ServiceName = "farmprices",
    [string]$RepoUrl   = "https://github.com/richowen/Inventory-Prices.git"
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

# Build the bootstrap script as a plain string (PowerShell expands variables here).
# Base64-encode it so it survives the SSH argument boundary intact — no quoting or
# newline issues regardless of what characters end up in the paths/URLs.
$script = @"
set -e
if [ ! -d $RepoDir/.git ]; then
  echo '[remote] Repo not found - cloning $RepoUrl'
  git clone --branch $Branch $RepoUrl $RepoDir
  echo '[remote] Clone complete'
fi
export REPO_DIR=$RepoDir
export APP_DIR=$AppDir
export BRANCH=$Branch
export SERVICE_NAME=$ServiceName
export REPO_URL=$RepoUrl
bash $RepoDir/farmprices/deploy/remote_deploy.sh
"@

$encoded = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($script))

Write-Step "Running remote deploy on $PiUser@$PiHost"
ssh "$PiUser@$PiHost" "echo $encoded | base64 -d | bash"
if ($LASTEXITCODE -ne 0) {
    throw "Remote deploy failed."
}

Write-Step "Deployment completed successfully"
