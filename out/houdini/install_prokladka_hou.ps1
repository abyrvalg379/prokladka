# install_prokladka_hou.ps1 — PROKLADKA Houdini installer (double-click via .bat)
# Копирует package, создаёт packages json, добавляет полку в видимый набор.
# Запускается: install_PROKLADKA.bat (double-click) или вручную:
#   powershell -NoProfile -ExecutionPolicy Bypass -File install_prokladka_hou.ps1

$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "package\prokladka\houdini"

if (-not (Test-Path (Join-Path $src "toolbar\prokladka.shelf"))) {
    Write-Host "[FAIL] package не найден рядом со скриптом: $src" -ForegroundColor Red
    exit 1
}

# ── 1. Найти папку префов Houdini (самая свежая Documents\houdini*) ─────────
$docs = Join-Path $env:USERPROFILE "Documents"
$prefs = Get-ChildItem -Path $docs -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "^houdini\d+\.\d+$" } |
    Sort-Object { [version]$_.Name.Substring(7) } -Descending
if (-not $prefs) {
    Write-Host "[FAIL] Не найдено $docs\houdini*" -ForegroundColor Red
    Write-Host "       Запусти Houdini один раз (создаст префы), потом снова этот установщик."
    exit 1
}
$pref = $prefs[0].FullName
Write-Host "[OK  ] Pref dir: $pref"

# ── 2. Houdini запущен? ──────────────────────────────────────────────────────
$houdiniRunning = [bool](Get-Process -Name "houdini" -ErrorAction SilentlyContinue)

# ── 3. Скопировать package (robocopy /MIR — надёжное зеркалирование) ────────
$dst = Join-Path $pref "prokladka\houdini"
robocopy $src $dst /MIR /NJH /NJS /NDL /NFL | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Host "[FAIL] robocopy exit $LASTEXITCODE" -ForegroundColor Red
    exit 1
}
Write-Host "[OK  ] Package -> $dst"

# ── 4. packages/prokladka.json ───────────────────────────────────────────────
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

# Без BOM — Houdini не переварит BOM-префикс в json
[IO.File]::WriteAllText($jsonPath, $body)
Write-Host "[OK  ] $jsonPath"

# ── 5. Видимость полки (только при закрытом Houdini) ────────────────────────
$shelfPath = Join-Path $pref "toolbar\default.shelf"
if ($houdiniRunning) {
    Write-Host "[SKIP] Houdini запущен — видимость не трогаю." -ForegroundColor Yellow
    Write-Host "       После старта: '+' на панели полок -> галка PROKLADKA (один раз)."
} elseif (-not (Test-Path $shelfPath)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $pref "toolbar") | Out-Null
    $content = @"
<?xml version="1.0" encoding="UTF-8"?>
<shelfDocument>
  <shelfSetEdit name="shelf_set_prokladka" fileLocation="$unixPath/toolbar/prokladka.shelf">
    <addMemberToolshelf name="prokladka" inPosition="15" />
  </shelfSetEdit>
</shelfDocument>
"@
    [IO.File]::WriteAllText($shelfPath, $content)
    Write-Host "[OK  ] default.shelf создан, полка будет видна"
} else {
    $content = Get-Content $shelfPath -Raw -Encoding UTF8
    if ($content -match "prokladka\.shelf") {
        Write-Host "[OK  ] Видимость полки уже настроена"
    } else {
        Copy-Item $shelfPath "$shelfPath.bak_prokladka" -Force
        $edit = "  <shelfSetEdit name=""shelf_set_prokladka"" fileLocation=""$unixPath/toolbar/prokladka.shelf"">`n    <addMemberToolshelf name=""prokladka"" inPosition=""15"" />`n  </shelfSetEdit>`n"
        $content = $content -replace "</shelfDocument>", ($edit + "</shelfDocument>")
        [IO.File]::WriteAllText($shelfPath, $content)
        Write-Host "[OK  ] Полка добавлена в видимый набор (бэкап: default.shelf.bak_prokladka)"
    }
}

Write-Host ""
Write-Host "INSTALLATION COMPLETE. Запускай Houdini — вкладка PROKLADKA на полке." -ForegroundColor Green
