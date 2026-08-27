# scripts/criar_atalho.ps1
#
# Cria o atalho "HALO" na area de trabalho, com o icone proprio.
#
# O atalho aponta para o pythonw.exe do ambiente virtual do projeto --
# pythonw, e nao python, porque pythonw nao abre a janela preta do console
# junto com o programa.
#
# Rode com:  powershell -ExecutionPolicy Bypass -File scripts\criar_atalho.ps1

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonw = Join-Path $raiz ".venv\Scripts\pythonw.exe"
$script = Join-Path $raiz "main.py"
$icone = Join-Path $raiz "assets\halo.ico"

foreach ($p in @($pythonw, $script, $icone)) {
    if (-not (Test-Path $p)) { throw "nao encontrado: $p" }
}

# A area de trabalho pode estar redirecionada para o OneDrive; sempre
# perguntar ao Windows onde ela esta, nunca montar o caminho na mao.
$desktop = [Environment]::GetFolderPath('Desktop')
$atalho = Join-Path $desktop "HALO.lnk"

$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($atalho)
$lnk.TargetPath = $pythonw
$lnk.Arguments = '"' + $script + '"'
$lnk.WorkingDirectory = $raiz
$lnk.IconLocation = "$icone,0"
$lnk.Description = "HALO - Ensaios de Emissao CISPR 15"
$lnk.WindowStyle = 1
$lnk.Save()

Write-Output "atalho criado: $atalho"
Write-Output "  alvo:  $pythonw"
Write-Output "  args:  $script"
Write-Output "  icone: $icone"
