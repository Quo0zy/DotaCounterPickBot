param(
    [string]$OutputPath = "data\seed_immortal.json",
    [ValidateRange(1, 30)]
    [int]$Days = 7,
    [string]$ApiToken = $env:STRATZ_API_TOKEN
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ApiToken)) {
    throw "Set STRATZ_API_TOKEN or pass -ApiToken. A free token is available at https://stratz.com/api."
}

$query = @'
query HeroWinDayStats(
  $days: Int,
  $ranks: [RankBracket!],
  $positions: [MatchPlayerPositionType!],
  $regions: [BasicRegionType!],
  $gameModes: [GameModeEnumType!]
) {
  heroStats {
    winDay(
      take: $days
      bracketIds: $ranks
      positionIds: $positions
      regionIds: $regions
      gameModeIds: $gameModes
    ) {
      day
      heroId
      winCount
      matchCount
    }
  }
}
'@

$variables = [ordered]@{
    days = $Days
    ranks = @("IMMORTAL")
    positions = @()
    regions = @()
    gameModes = @("ALL_PICK_RANKED")
}

$requestBody = [ordered]@{
    query = $query
    variables = $variables
} | ConvertTo-Json -Depth 8

Write-Host "Downloading $Days days of Immortal ranked All Pick stats from STRATZ..."
$response = Invoke-RestMethod `
    -Uri "https://api.stratz.com/graphql" `
    -Method Post `
    -ContentType "application/json" `
    -Headers @{
        Authorization = "Bearer $ApiToken"
        "User-Agent" = "DotaCounterPeak/1.0"
    } `
    -Body $requestBody `
    -TimeoutSec 90

if ($response.errors) {
    $messages = @($response.errors | ForEach-Object { $_.message }) -join "; "
    throw "STRATZ GraphQL error: $messages"
}

$dailyRows = @($response.data.heroStats.winDay)
if ($dailyRows.Count -eq 0) {
    throw "STRATZ returned no Immortal statistics. The existing seed was not changed."
}

$heroRows = @(Invoke-RestMethod -Uri "https://api.opendota.com/api/heroes" -TimeoutSec 60)
$heroNames = @{}
foreach ($hero in $heroRows) {
    $heroNames[[string]$hero.id] = [string]$hero.localized_name
}

$totalHeroPicks = [double](
    $dailyRows |
        Measure-Object -Property matchCount -Sum
).Sum
$estimatedMatches = $totalHeroPicks / 10.0
if ($estimatedMatches -le 0) {
    throw "STRATZ returned an invalid match count. The existing seed was not changed."
}

$seedHeroes = @(
    $dailyRows |
        Group-Object -Property heroId |
        ForEach-Object {
            $heroId = [string]$_.Name
            $matches = [double](
                $_.Group |
                    Measure-Object -Property matchCount -Sum
            ).Sum
            $wins = [double](
                $_.Group |
                    Measure-Object -Property winCount -Sum
            ).Sum

            if ($matches -gt 0 -and $heroNames.ContainsKey($heroId)) {
                [ordered]@{
                    name = $heroNames[$heroId]
                    win_rate = [Math]::Round(100.0 * $wins / $matches, 2)
                    pick_rate = [Math]::Round(100.0 * $matches / $estimatedMatches, 2)
                }
            }
        } |
        Where-Object { $null -ne $_ } |
        Sort-Object `
            @{ Expression = { [double]$_.win_rate }; Descending = $true },
            @{ Expression = { [double]$_.pick_rate }; Descending = $true }
)

if ($seedHeroes.Count -lt 120) {
    throw "STRATZ returned only $($seedHeroes.Count) heroes. The existing seed was not changed."
}

$payload = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    source = "STRATZ GraphQL API"
    source_url = "https://api.stratz.com/graphql"
    rank = "IMMORTAL"
    game_mode = "ALL_PICK_RANKED"
    period_days = $Days
    hero_count = $seedHeroes.Count
    heroes = $seedHeroes
}

$root = Split-Path -Parent $PSScriptRoot
$absoluteOutputPath = Join-Path $root $OutputPath
$outputDirectory = Split-Path -Parent $absoluteOutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$temporaryPath = "$absoluteOutputPath.tmp"
$payload |
    ConvertTo-Json -Depth 8 |
    Set-Content -Path $temporaryPath -Encoding UTF8
Move-Item -LiteralPath $temporaryPath -Destination $absoluteOutputPath -Force

Write-Host "Saved $($seedHeroes.Count) Immortal heroes to $absoluteOutputPath"
