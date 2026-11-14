<#
  instalar_ssas2019.ps1 - Instala SQL Server 2019 Developer SOLO con Analysis Services Multidimensional
  (instancia con nombre SSAS2019), que todavia soporta Data Mining (SQL Server 2022/2025 lo discontinuaron).
  Ejecutar en PowerShell COMO ADMINISTRADOR:
     powershell -ExecutionPolicy Bypass -File instalar_ssas2019.ps1
#>
param([string]$Media = (Join-Path $PSScriptRoot "SQL2019_media"))  # carpeta donde se descargo el paquete de SQL Server 2019 Developer
$ErrorActionPreference = "Stop"
$usuario = [Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Host "Administrador de SSAS que se configurara: $usuario"

# 1) Extraer el paquete descargado
$exe = Get-ChildItem $Media -Filter "SQLServer2019-*.exe" -Recurse | Select-Object -First 1
if (-not $exe) { throw "No se encontro el paquete SQLServer2019-*.exe en $Media" }
$extraido = Join-Path $Media "extraido"
if (-not (Test-Path (Join-Path $extraido "setup.exe"))) {
  Write-Host "Extrayendo $($exe.Name)..."
  Start-Process $exe.FullName -ArgumentList "/Q /X:`"$extraido`"" -Wait
}

# 2) Instalar solo Analysis Services (modo Multidimensional y Data Mining)
Write-Host "Instalando SQL Server 2019 Analysis Services (instancia SSAS2019). Tarda entre 5 y 15 minutos..."
$argumentos = @(
  "/Q", "/ACTION=Install", "/FEATURES=AS", "/INSTANCENAME=SSAS2019",
  "/ASSERVERMODE=MULTIDIMENSIONAL", "/ASSYSADMINACCOUNTS=`"$usuario`"",
  "/ASSVCSTARTUPTYPE=Automatic", "/IACCEPTSQLSERVERLICENSETERMS", "/SUPPRESSPRIVACYSTATEMENTNOTICE",
  "/UPDATEENABLED=0", "/ENU", "/INDICATEPROGRESS"
)
$p = Start-Process (Join-Path $extraido "setup.exe") -ArgumentList $argumentos -Wait -PassThru -NoNewWindow
Write-Host "Setup finalizo con codigo $($p.ExitCode) (0 = correcto, 3010 = correcto pero pide reiniciar)"

# 3) Verificar el servicio
Get-Service 'MSOLAP$SSAS2019' | Format-Table Name, Status, StartType
$resumen = "C:\Program Files\Microsoft SQL Server\150\Setup Bootstrap\Log\Summary.txt"
if (Test-Path $resumen) { Get-Content $resumen -TotalCount 25 }
