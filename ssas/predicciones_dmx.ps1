<#
  predicciones_dmx.ps1 - Obtiene de SSAS (DMX) los casos de prueba (holdout 30%) de cada estructura y la
  probabilidad predicha por cada modelo, para evaluar con curva ROC / AUC (mineria\predicciones_ssas_*.csv).
  Uso: powershell -ExecutionPolicy Bypass -File predicciones_dmx.ps1 [-Servidor localhost\SSAS2019]
#>
param([string]$Servidor = "localhost\SSAS2019")
$ErrorActionPreference = "Stop"
[void][Reflection.Assembly]::LoadFrom("C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\SSAS\Microsoft.AnalysisServices.AdomdClient.dll")
$cn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection ("Data Source=$Servidor;Catalog=SiniestrosVialesOLAP")
$cn.Open()
$raiz = Split-Path $PSScriptRoot -Parent

function Exportar($dmx, $archivo) {
  $cmd = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdCommand ($dmx, $cn)
  $cmd.CommandTimeout = 0
  $rd = $cmd.ExecuteReader()
  $sw = New-Object IO.StreamWriter ((Join-Path $raiz "mineria\$archivo"), $false, (New-Object Text.UTF8Encoding $false))
  $cols = for ($i = 0; $i -lt $rd.FieldCount; $i++) { $rd.GetName($i) -replace '^.*\.', '' -replace '[\[\]]', '' }
  $sw.WriteLine(($cols -join ";"))
  $n = 0
  while ($rd.Read()) {
    $vals = for ($i = 0; $i -lt $rd.FieldCount; $i++) { $v = $rd.GetValue($i); if ($v -is [double]) { $v.ToString([Globalization.CultureInfo]::InvariantCulture) } else { "$v" } }
    $sw.WriteLine(($vals -join ";")); $n++
  }
  $rd.Close(); $sw.Close()
  Write-Output "$archivo : $n filas"
}

# Casos de prueba de cada estructura (IsTestCase) con la probabilidad de cada modelo (PREDICTION JOIN)
$colsS = "Hora","FranjaHoraria","TipoDia","DiaSemana","Estacion","Contexto","Comuna","Zona","TipoVia","VehiculoVictima","Contraparte","TotalVictimas"
$sel = ($colsS | ForEach-Object { "[$_]" }) -join ", "
foreach ($m in "Arbol de Decision - Gravedad", "Naive Bayes - Gravedad", "Regresion Logistica - Gravedad", "Red Neuronal - Gravedad") {
  $on = ($colsS | ForEach-Object { "[$m].[$_] = t.[$_]" }) -join " AND "
  $dmx = "SELECT t.[SiniestroID], t.[Gravedad], PredictProbability([$m].[Gravedad], 'GRAVE O MORTAL') AS P " +
         "FROM [$m] PREDICTION JOIN (SELECT [SiniestroID], [Gravedad], $sel FROM [MS Gravedad Siniestros].CASES WHERE IsTestCase()) AS t ON $on"
  Exportar $dmx ("predicciones_ssas_" + ($m -replace '[^A-Za-z]', '_') + ".csv")
}
$colsV = "Edad","Hora","RangoEtario","Sexo","Vehiculo","TipoVia","FranjaHoraria","TipoDia","Zona"
$selV = ($colsV | ForEach-Object { "[$_]" }) -join ", "
foreach ($m in "Arbol de Decision - Victima Fatal", "Naive Bayes - Victima Fatal") {
  $usar = if ($m -like "Naive*") { $colsV | Where-Object { $_ -ne "Edad" } } else { $colsV }
  $on = ($usar | ForEach-Object { "[$m].[$_] = t.[$_]" }) -join " AND "
  $dmx = "SELECT t.[VictimaID], t.[Desenlace], PredictProbability([$m].[Desenlace], 'FALLECIO') AS P " +
         "FROM [$m] PREDICTION JOIN (SELECT [VictimaID], [Desenlace], $selV FROM [MS Victima Fatal].CASES WHERE IsTestCase()) AS t ON $on"
  Exportar $dmx ("predicciones_ssas_" + ($m -replace '[^A-Za-z]', '_') + ".csv")
}
$cn.Close()
