# install_prokladka_hou.ps1 — PROKLADKA Houdini installer (double-click via .bat)
# Копирует package + создаёт packages json.
# Запускается: install_PROKLADKA.bat (double-click) или вручную:
#   powershell -NoProfile -ExecutionPolicy Bypass -File install_prokladka_hou.ps1

$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "package\prokladka\houdini"

if (-not (Test-Path (Join-Path $src "toolbar\prokladka.shelf"))) {
    Write-Host "[FAIL] package не найден рядом со скриптом: $src" -ForegroundColor Red
    exit 1
}

# ── 1. Найти папку префов Houdini (houdiniMAJOR.MINOR, самая свежая) ─────────
$docs = Join-Path $env:USERPROFILE "Documents"
$prefs = Get-ChildItem -Path $docs -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "^houdini\d+\.\d+$" } |
    Sort-Object { [version]$_.Name.Substring(7) } -Descending
if (-not $prefs) {
    Write-Host "[FAIL] Не найдено $docs\houdiniMAJOR.MINOR" -ForegroundColor Red
    Write-Host "       Запусти Houdini один раз (создаст префы), потом снова этот установщик."
    exit 1
}
$pref = $prefs[0].FullName
Write-Host "[OK  ] Pref dir: $pref"

# ── 2. Скопировать package (robocopy /MIR — надёжное зеркалирование) ────────
$dst = Join-Path $pref "prokladka\houdini"
robocopy $src $dst /MIR /NJH /NJS /NDL /NFL | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Host "[FAIL] robocopy exit $LASTEXITCODE" -ForegroundColor Red
    exit 1
}
Write-Host "[OK  ] Package -> $dst"

# ── 3. packages/prokladka.json (без BOM — Houdini его не переваривает) ──────
$packagesDir = Join-Path $pref "packages"
New-Item -ItemType Directory -Force -Path $packagesDir | Out-Null
$jsonPath = Join-Path $packagesDir "prokladka.json"
$unixPath = $dst -replace "\\", "/"
$body = @"
{
    "env": [
        {"PROKLADKA": "$unixPath"}
    ],
    "path": ["`$PROKLADKA"]
}
"@
[IO.File]::WriteAllText($jsonPath, $body)
Write-Host "[OK  ] $jsonPath"

Write-Host ""
Write-Host "INSTALLATION COMPLETE." -ForegroundColor Green
Write-Host "Запусти Houdini -> '+' в строке вкладок полок -> галка PROKLADKA (один раз)."
