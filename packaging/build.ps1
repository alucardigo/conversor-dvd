<#
.SYNOPSIS
  Gera o executável (dist\ConversorDVD) e o instalador (installer\out) do Conversor de DVD.

.DESCRIPTION
  1. Roda os testes rápidos (pulável com -PularTestes).
  2. Empacota com PyInstaller: ConversorDVD.exe (janela) e conversor-dvd.exe (linha de comando).
  3. Copia ffmpeg.exe e ffprobe.exe para dist\ConversorDVD\ffmpeg\bin.
  4. Compila o instalador com o Inno Setup 6 (ISCC.exe).
  Não precisa de administrador. Os binários NÃO são assinados.

.PARAMETER FFmpeg
  Pasta com ffmpeg.exe e ffprobe.exe. Padrão: pasta do Scoop.

.PARAMETER Inno
  Caminho do ISCC.exe. Se vazio, procura no PATH e nas pastas usuais de instalação.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#>
param(
    [string]$FFmpeg = "$env:USERPROFILE\scoop\apps\ffmpeg\current\bin",
    [string]$Inno = "",
    [switch]$PularTestes
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

function Executar([string]$programa, [string[]]$argumentos) {
    & $programa @argumentos
    if ($LASTEXITCODE -ne 0) {
        throw "falhou: $programa $($argumentos -join ' ') (código $LASTEXITCODE)"
    }
}

$versao = (Select-String -Path "conversor_dvd\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Conversor de DVD $versao"

if (-not $PularTestes) {
    Write-Host "`n[1/4] Testes rápidos"
    Executar "python" @("-m", "pytest", "-q", "-m", "not integracao")
}

Write-Host "`n[2/4] PyInstaller"
Executar "python" @("-m", "PyInstaller", "packaging\ConversorDVD.spec", "--noconfirm", "--distpath", "dist", "--workpath", "build")

Write-Host "`n[3/4] ffmpeg dentro da pasta do programa"
$destino = "dist\ConversorDVD\ffmpeg"
New-Item -ItemType Directory -Force -Path "$destino\bin" | Out-Null
foreach ($arquivo in @("ffmpeg.exe", "ffprobe.exe")) {
    $origem = Join-Path $FFmpeg $arquivo
    if (-not (Test-Path $origem)) { throw "não achei $origem (use -FFmpeg com a pasta certa)" }
    Copy-Item $origem "$destino\bin\" -Force
}
$pastaPai = Split-Path -Parent $FFmpeg
foreach ($aviso in @("LICENSE", "README.txt")) {
    $caminho = Join-Path $pastaPai $aviso
    if (Test-Path $caminho) { Copy-Item $caminho "$destino\" -Force }
}

Write-Host "`n[4/4] Instalador"
if (-not $Inno) {
    $candidatos = @(
        (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue).Source,
        "D:\Dev\Tools\InnoSetup6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $Inno = $candidatos | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}
if (-not $Inno) {
    Write-Host "`nISCC.exe (Inno Setup 6) não encontrado. O programa já está em dist\ConversorDVD."
    Write-Host "Instale o Inno Setup 6 (sem admin: /CURRENTUSER) e rode de novo, ou passe -Inno <caminho>."
    exit 2
}
Executar $Inno @("/DVersao=$versao", "packaging\ConversorDVD.iss")

$saida = "installer\out\ConversorDVD-Setup-$versao.exe"
$hash = (Get-FileHash $saida -Algorithm SHA256).Hash
Write-Host "`nInstalador: $saida"
Write-Host "SHA-256:    $hash"
