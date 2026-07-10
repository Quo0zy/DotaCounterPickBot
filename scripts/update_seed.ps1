param(
    [string]$OutputPath = "data\seed_matchups.json",
    [int]$MinGames = 20
)

$ErrorActionPreference = "Stop"

function Get-OpenDotaJson {
    param(
        [string]$Url,
        [string]$CachePath
    )

    if ($CachePath -and (Test-Path $CachePath)) {
        $cachedJson = Get-Content -Path $CachePath -Raw -Encoding UTF8
        return ($cachedJson | ConvertFrom-Json)
    }

    for ($attempt = 1; $attempt -le 5; $attempt += 1) {
        $json = curl.exe -s -L --max-time 45 $Url
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($json)) {
            Start-Sleep -Seconds 5
            continue
        }

        if ($json -like '*minute rate limit exceeded*') {
            Write-Host "Rate limit reached, waiting before retry..."
            Start-Sleep -Seconds 70
            continue
        }

        $parsed = $json | ConvertFrom-Json
        if ($CachePath) {
            Set-Content -Path $CachePath -Value $json -Encoding UTF8
        }
        return $parsed
    }

    throw "Failed to download $Url"
}

$root = Split-Path -Parent $PSScriptRoot
$absoluteOutputPath = Join-Path $root $OutputPath
$outputDirectory = Split-Path -Parent $absoluteOutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$cacheDirectory = Join-Path $outputDirectory "opendota_raw"
New-Item -ItemType Directory -Force -Path $cacheDirectory | Out-Null

$heroesUrl = "http://api.opendota.com/api/heroes"
$heroesCachePath = Join-Path $cacheDirectory "heroes.json"
$heroRows = @(Get-OpenDotaJson $heroesUrl $heroesCachePath | ForEach-Object { $_ })
$heroNames = @{}

foreach ($hero in $heroRows) {
    $heroNames[[string]$hero.id] = [string]$hero.localized_name
}

$seedHeroes = New-Object System.Collections.Generic.List[object]
$skippedHeroes = New-Object System.Collections.Generic.List[string]
$processed = 0

foreach ($hero in $heroRows) {
    $processed += 1
    Write-Host "[$processed/$($heroRows.Count)] $($hero.localized_name)"

    $matchupsUrl = "http://api.opendota.com/api/heroes/$($hero.id)/matchups"
    $matchupsCachePath = Join-Path $cacheDirectory "hero_$($hero.id)_matchups.json"
    $matchupRows = @(Get-OpenDotaJson $matchupsUrl $matchupsCachePath | ForEach-Object { $_ })
    $knownMatchups = @(
        $matchupRows |
            Where-Object {
                $heroNames.ContainsKey([string]$_.hero_id) -and
                [int]$_.games_played -ge $MinGames
            }
    )

    if ($knownMatchups.Count -lt 6) {
        $knownMatchups = @(
            $matchupRows |
                Where-Object { $heroNames.ContainsKey([string]$_.hero_id) }
        )
    }

    if ($knownMatchups.Count -lt 3) {
        $skippedHeroes.Add([string]$hero.localized_name)
        continue
    }

    $byBestWinrate = @(
        $knownMatchups |
            Sort-Object `
                @{ Expression = { [double]$_.wins / [double]$_.games_played }; Descending = $true },
                @{ Expression = { [int]$_.games_played }; Descending = $true }
    )
    $byWorstWinrate = @(
        $knownMatchups |
            Sort-Object `
                @{ Expression = { [double]$_.wins / [double]$_.games_played }; Descending = $false },
                @{ Expression = { [int]$_.games_played }; Descending = $true }
    )

    $goodAgainst = @(
        $byBestWinrate |
            Select-Object -First 3 |
            ForEach-Object { $heroNames[[string]$_.hero_id] }
    )
    $badAgainst = @(
        $byWorstWinrate |
            Select-Object -First 3 |
            ForEach-Object { $heroNames[[string]$_.hero_id] }
    )

    $seedHeroes.Add([ordered]@{
        name = [string]$hero.localized_name
        good_against = $goodAgainst
        bad_against = $badAgainst
    })

    Start-Sleep -Milliseconds 1100
}

$payload = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    source = "OpenDota API"
    source_urls = @(
        "http://api.opendota.com/api/heroes",
        "http://api.opendota.com/api/heroes/{hero_id}/matchups"
    )
    min_games = $MinGames
    hero_count = $seedHeroes.Count
    skipped_heroes = $skippedHeroes
    heroes = $seedHeroes
}

$payload |
    ConvertTo-Json -Depth 8 |
    Set-Content -Path $absoluteOutputPath -Encoding UTF8

Write-Host "Saved $($seedHeroes.Count) heroes to $absoluteOutputPath"
if ($skippedHeroes.Count -gt 0) {
    Write-Host "Skipped: $($skippedHeroes -join ', ')"
}
