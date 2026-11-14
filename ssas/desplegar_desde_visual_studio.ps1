<#
  desplegar_desde_visual_studio.ps1 - Despliega y procesa el resultado de COMPILAR el proyecto de Visual Studio
  (visual_studio\CuboSiniestrosViales\bin\CuboSiniestrosViales.asdatabase), igual que el boton "Implementar".
  Uso: powershell -ExecutionPolicy Bypass -File desplegar_desde_visual_studio.ps1 [-Servidor localhost\SSAS2019]
#>
param([string]$Servidor = "localhost\SSAS2019")
$ErrorActionPreference = "Stop"
$dir = "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\SSAS"
[void][Reflection.Assembly]::LoadFrom("$dir\Microsoft.AnalysisServices.Core.dll")
[void][Reflection.Assembly]::LoadFrom("$dir\Microsoft.AnalysisServices.dll")
$raiz = Split-Path $PSScriptRoot -Parent
$asdb = Join-Path $raiz "visual_studio\CuboSiniestrosViales\bin\CuboSiniestrosViales.asdatabase"
$def = [IO.File]::ReadAllText($asdb) -replace '^\s*<\?xml[^>]*\?>', ''
# el asistente de implementacion quita las propiedades de solo lectura antes de enviar el comando
$def = $def -replace '<(CreatedTimestamp|LastSchemaUpdate|LastProcessed|LastUpdate|State|CurrentStorageMode|EstimatedSize|EstimatedRows)>[^<]*</\1>\s*', ''
$xmla = "<Create AllowOverwrite=`"true`" xmlns=`"http://schemas.microsoft.com/analysisservices/2003/engine`"><ObjectDefinition>$def</ObjectDefinition></Create>"
$srv = New-Object Microsoft.AnalysisServices.Server
$srv.Connect($Servidor)
function Ejecutar($cmd, $paso) {
  $res = $srv.Execute($cmd)
  $err = foreach ($r in $res) { foreach ($m in $r.Messages) { if ($m -is [Microsoft.AnalysisServices.XmlaError]) { $m.Description } } }
  if ($err) { throw "$paso fallo: $($err -join ' | ')" }
  Write-Output "$paso OK"
}
Ejecutar $xmla "Implementacion (Create AllowOverwrite)"
$sw = [Diagnostics.Stopwatch]::StartNew()
Ejecutar "<Process xmlns=`"http://schemas.microsoft.com/analysisservices/2003/engine`"><Type>ProcessFull</Type><Object><DatabaseID>SiniestrosVialesOLAP</DatabaseID></Object></Process>" "Procesamiento completo (cubo + mineria)"
Write-Output ("  tiempo de procesamiento: {0:N0} s" -f $sw.Elapsed.TotalSeconds)
# el rol del proyecto no trae miembros: se agrega el usuario actual (como DeployRolesRetainMembers)
$srv.Refresh(); $db = $srv.Databases.FindByName("SiniestrosVialesOLAP")
$rol = $db.Roles.FindByName("Lectores"); $u = [Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($rol -and -not ($rol.Members | Where-Object { $_.Name -eq $u })) { [void]$rol.Members.Add((New-Object Microsoft.AnalysisServices.RoleMember ($u))); $rol.Update() }
Write-Output ("Base: {0} - estado {1} - cubos: {2} - dimensiones: {3} - estructuras de mineria: {4} - modelos: {5}" -f $db.Name, $db.State, $db.Cubes.Count, $db.Dimensions.Count, $db.MiningStructures.Count, (($db.MiningStructures | ForEach-Object { $_.MiningModels.Count }) | Measure-Object -Sum).Sum)
foreach ($ms in $db.MiningStructures) { foreach ($mm in $ms.MiningModels) { Write-Output ("  {0,-36} {1,-32} {2}" -f $mm.Name, $mm.Algorithm, $mm.State) } }
$srv.Disconnect()
