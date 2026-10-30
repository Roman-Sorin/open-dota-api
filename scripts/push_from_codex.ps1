param(
    [string]$Remote = "origin",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$expectedRemote = "https://github.com/Roman-Sorin/open-dota-api.git"
$actualRemote = (& git remote get-url $Remote).Trim()
if ($LASTEXITCODE -ne 0 -or $actualRemote -ne $expectedRemote) {
    throw "This push helper only supports $expectedRemote."
}

$token = (& gh auth token).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
    throw "GitHub CLI is not authenticated in Windows PowerShell."
}

try {
    $basicAuth = [Convert]::ToBase64String(
        [Text.Encoding]::ASCII.GetBytes("x-access-token:$token")
    )
    $env:GIT_CONFIG_COUNT = "1"
    $env:GIT_CONFIG_KEY_0 = "http.https://github.com/.extraheader"
    $env:GIT_CONFIG_VALUE_0 = "Authorization: Basic $basicAuth"
    $env:GIT_TERMINAL_PROMPT = "0"

    & git -c credential.helper= -c credential.https://github.com.helper= push $Remote $Branch
    if ($LASTEXITCODE -ne 0) {
        throw "Git push failed with exit code $LASTEXITCODE."
    }
}
finally {
    Remove-Item Env:GIT_CONFIG_COUNT, Env:GIT_CONFIG_KEY_0, Env:GIT_CONFIG_VALUE_0, Env:GIT_TERMINAL_PROMPT -ErrorAction SilentlyContinue
    $token = $null
    $basicAuth = $null
}
