<#
  consultas_dmx.ps1 - Consulta los modelos de mineria de datos de SSAS con DMX (Data Mining Extensions)
  y guarda los resultados en mineria\resultados_ssas.json y ssas\resultado_consultas_dmx.txt.
  Uso: powershell -ExecutionPolicy Bypass -File consultas_dmx.ps1 [-Servidor localhost\SSAS2019]
#>
param([string]$Servidor = "localhost\SSAS2019", [string]$ServidorSQL = "localhost")
$ErrorActionPreference = "Stop"
[void][Reflection.Assembly]::LoadFrom("C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\SSAS\Microsoft.AnalysisServices.AdomdClient.dll")
$cn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection ("Data Source=$Servidor;Catalog=SiniestrosVialesOLAP")
$cn.Open()
$txt = New-Object System.Collections.Generic.List[string]

function Q($dmx, $titulo) {
  $cmd = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdCommand ($dmx, $cn)
  $rd = $cmd.ExecuteReader()
  $filas = @()
  while ($rd.Read()) {
    $o = [ordered]@{}
    for ($i = 0; $i -lt $rd.FieldCount; $i++) {
      $n = $rd.GetName($i) -replace '^.*\.', '' -replace '[\[\]]', ''
      $v = $rd.GetValue($i); if ($v -is [DBNull]) { $v = $null }
      $o[$n] = $v
    }
    $filas += [pscustomobject]$o
  }
  $rd.Close()
  $txt.Add("==== $titulo"); $txt.Add($dmx.Trim()); $txt.Add(($filas | Select-Object -First 25 | Format-Table -AutoSize | Out-String -Width 250))
  return ,$filas
}
$R = @{}

# ------------------------------------------------------------ 1. Precision de los clasificadores (casos de prueba = 30% holdout)
$R.precision_gravedad = Q @"
CALL SystemGetAccuracyResults([MS Gravedad Siniestros], [Arbol de Decision - Gravedad], [Naive Bayes - Gravedad],
     [Regresion Logistica - Gravedad], [Red Neuronal - Gravedad], 2, 'Gravedad', 'GRAVE O MORTAL')
"@ "Precision de modelos de gravedad (casos de prueba)"
$R.precision_victima = Q @"
CALL SystemGetAccuracyResults([MS Victima Fatal], [Arbol de Decision - Victima Fatal], [Naive Bayes - Victima Fatal], 2, 'Desenlace', 'FALLECIO')
"@ "Precision de modelos de victima fatal (casos de prueba)"

# ------------------------------------------------------------ 2. Arbol de decision: hojas con mayor probabilidad de gravedad
$hojas = Q @"
SELECT FLATTENED NODE_UNIQUE_NAME, NODE_DESCRIPTION, NODE_SUPPORT,
  (SELECT ATTRIBUTE_VALUE, [PROBABILITY] FROM NODE_DISTRIBUTION) AS D
FROM [Arbol de Decision - Gravedad].CONTENT WHERE NODE_TYPE = 4
"@ "Hojas del arbol de decision (gravedad)"
$R.arbol_hojas = $hojas | Where-Object { "$($_.ATTRIBUTE_VALUE)" -eq "GRAVE O MORTAL" } | Sort-Object PROBABILITY -Descending | Select-Object -First 12
$R.arbol_total_hojas = ($hojas | Select-Object -ExpandProperty NODE_UNIQUE_NAME -Unique).Count
$hojasV = Q @"
SELECT FLATTENED NODE_UNIQUE_NAME, NODE_DESCRIPTION, NODE_SUPPORT,
  (SELECT ATTRIBUTE_VALUE, [PROBABILITY] FROM NODE_DISTRIBUTION) AS D
FROM [Arbol de Decision - Victima Fatal].CONTENT WHERE NODE_TYPE = 4
"@ "Hojas del arbol de decision (victima fatal)"
$R.arbol_victima_hojas = $hojasV | Where-Object { "$($_.ATTRIBUTE_VALUE)" -eq "FALLECIO" } | Sort-Object PROBABILITY -Descending | Select-Object -First 10

# ------------------------------------------------------------ 3. Predicciones de escenarios (consultas singleton)
$escenarios = @(
  @{ n = "Peaton vs colectivo, avenida, madrugada";       v = "'PEATON' AS [VehiculoVictima], 'TRANSPORTE PUBLICO' AS [Contraparte], 'AVENIDA' AS [TipoVia], '1. Madrugada (00-05)' AS [FranjaHoraria]" },
  @{ n = "Moto vs objeto fijo, fin de semana, madrugada"; v = "'MOTO' AS [VehiculoVictima], 'OBJETO FIJO' AS [Contraparte], 'Fin de semana' AS [TipoDia], '1. Madrugada (00-05)' AS [FranjaHoraria]" },
  @{ n = "Moto vs auto, Gral. Paz, noche";                v = "'MOTO' AS [VehiculoVictima], 'AUTO' AS [Contraparte], 'AV. GRAL. PAZ' AS [TipoVia], '4. Noche (18-23)' AS [FranjaHoraria]" },
  @{ n = "Ciclista vs auto, calle, tarde habil";          v = "'BICICLETA' AS [VehiculoVictima], 'AUTO' AS [Contraparte], 'CALLE' AS [TipoVia], '3. Tarde (12-17)' AS [FranjaHoraria], 'Dia habil' AS [TipoDia]" },
  @{ n = "Auto vs auto, avenida, tarde habil";            v = "'AUTO' AS [VehiculoVictima], 'AUTO' AS [Contraparte], 'AVENIDA' AS [TipoVia], '3. Tarde (12-17)' AS [FranjaHoraria], 'Dia habil' AS [TipoDia]" }
)
$modelos = "Arbol de Decision - Gravedad", "Naive Bayes - Gravedad", "Regresion Logistica - Gravedad", "Red Neuronal - Gravedad"
$R.escenarios = @()
foreach ($e in $escenarios) {
  $fila = [ordered]@{ Escenario = $e.n }
  foreach ($m in $modelos) {
    $res = Q "SELECT PredictProbability([Gravedad], 'GRAVE O MORTAL') AS P FROM [$m] NATURAL PREDICTION JOIN (SELECT $($e.v)) AS t" "Escenario: $($e.n) - $m"
    $fila[$m] = $res[0].P
  }
  $R['escenarios'] = @($R['escenarios']) + @([pscustomobject]$fila)
}
$escV = @(
  @{ n = "Peaton de 75 anios, mujer, avenida, noche";      v = "75 AS [Edad], '65 y mas' AS [RangoEtario], 'Femenino' AS [Sexo], 'PEATON' AS [Vehiculo], 'AVENIDA' AS [TipoVia], '4. Noche (18-23)' AS [FranjaHoraria]" },
  @{ n = "Motociclista de 25 anios, varon, autopista, madrugada"; v = "25 AS [Edad], '25-34' AS [RangoEtario], 'Masculino' AS [Sexo], 'MOTO' AS [Vehiculo], 'AUTOPISTA' AS [TipoVia], '1. Madrugada (00-05)' AS [FranjaHoraria]" },
  @{ n = "Ciclista de 30 anios, mujer, calle, tarde";      v = "30 AS [Edad], '25-34' AS [RangoEtario], 'Femenino' AS [Sexo], 'BICICLETA' AS [Vehiculo], 'CALLE' AS [TipoVia], '3. Tarde (12-17)' AS [FranjaHoraria]" }
)
$R.escenarios_victima = @()
foreach ($e in $escV) {
  $fila = [ordered]@{ Escenario = $e.n }
  foreach ($m in "Arbol de Decision - Victima Fatal", "Naive Bayes - Victima Fatal") {
    $res = Q "SELECT PredictProbability([Desenlace], 'FALLECIO') AS P FROM [$m] NATURAL PREDICTION JOIN (SELECT $($e.v)) AS t" "Escenario victima: $($e.n) - $m"
    $fila[$m] = $res[0].P
  }
  $R['escenarios_victima'] = @($R['escenarios_victima']) + @([pscustomobject]$fila)
}

# ------------------------------------------------------------ 4. Clustering de siniestros
$cl = Q @"
SELECT FLATTENED NODE_CAPTION, NODE_SUPPORT, NODE_DESCRIPTION,
  (SELECT ATTRIBUTE_VALUE, [PROBABILITY] FROM NODE_DISTRIBUTION WHERE ATTRIBUTE_NAME = 'Gravedad') AS D
FROM [Clustering - Siniestros].CONTENT WHERE NODE_TYPE = 5
"@ "Clusters de siniestros"
$R.clusters_siniestros = $cl | Where-Object { "$($_.ATTRIBUTE_VALUE)" -eq "GRAVE O MORTAL" } |
  Select-Object NODE_CAPTION, NODE_SUPPORT, PROBABILITY, @{ n = "NODE_DESCRIPTION"; e = { ($_.NODE_DESCRIPTION -split ',' | Select-Object -First 8) -join ',' } } |
  Sort-Object PROBABILITY -Descending

# ------------------------------------------------------------ 5. Clustering de comunas (prediccion Cluster() para cada comuna)
$sq = New-Object System.Data.SqlClient.SqlConnection ("Data Source=$ServidorSQL;Initial Catalog=SiniestrosVialesDW;Integrated Security=SSPI;TrustServerCertificate=True")
$sq.Open()
$dt = New-Object System.Data.DataTable
(New-Object System.Data.SqlClient.SqlDataAdapter ("SELECT * FROM dbo.vmin_PerfilComunas ORDER BY Comuna", $sq)).Fill($dt) | Out-Null
$sq.Close()
$R.clusters_comunas = @()
$inv = [Globalization.CultureInfo]::InvariantCulture
foreach ($row in $dt.Rows) {
  $vals = ($dt.Columns | Where-Object { $_.ColumnName -notin "Comuna","Zona" } | ForEach-Object { ([double]$row[$_.ColumnName]).ToString($inv) + " AS [" + $_.ColumnName + "]" }) -join ", "
  $res = Q "SELECT Cluster() AS C, ClusterProbability() AS P FROM [Clustering - Comunas] NATURAL PREDICTION JOIN (SELECT '$($row.Zona)' AS [Zona], $vals) AS t" "Cluster de $($row.Comuna)"
  $R['clusters_comunas'] = @($R['clusters_comunas']) + @([pscustomobject]@{ Comuna = $row.Comuna; Zona = $row.Zona; Cluster = $res[0].C; Probabilidad = $res[0].P })
}
$R.clusters_comunas_desc = Q "SELECT NODE_CAPTION, NODE_SUPPORT, NODE_DESCRIPTION FROM [Clustering - Comunas].CONTENT WHERE NODE_TYPE = 5" "Clusters de comunas"

# ------------------------------------------------------------ 6. Reglas de asociacion
$reglas = Q "SELECT NODE_DESCRIPTION, NODE_PROBABILITY, MSOLAP_NODE_SCORE, NODE_SUPPORT FROM [Reglas de Asociacion].CONTENT WHERE NODE_TYPE = 8" "Reglas de asociacion"
$items = Q "SELECT NODE_SUPPORT FROM [Reglas de Asociacion].CONTENT WHERE NODE_TYPE = 7" "Itemsets"
$R.asociacion_total_reglas = $reglas.Count
$R.asociacion_total_itemsets = $items.Count
$R.reglas_grave = $reglas | Where-Object { $_.NODE_DESCRIPTION -like "*-> Gravedad = GRAVE O MORTAL" } | Sort-Object MSOLAP_NODE_SCORE -Descending | Select-Object -First 12
$R.reglas_top = $reglas | Where-Object { $_.NODE_DESCRIPTION -notlike "*-> Gravedad = LEVE" } | Sort-Object MSOLAP_NODE_SCORE -Descending | Select-Object -First 12

# ------------------------------------------------------------ 7. Series de tiempo: pronostico 12 meses
$R.pronostico_siniestros = Q "SELECT FLATTENED PredictTimeSeries([Siniestros], 12) AS F FROM [Serie de Tiempo - Siniestros]" "Pronostico Siniestros 2026"
$R.pronostico_mortales = Q "SELECT FLATTENED PredictTimeSeries([Mortales], 12) AS F FROM [Serie de Tiempo - Siniestros]" "Pronostico Mortales 2026"

$cn.Close()
$raiz = Split-Path $PSScriptRoot -Parent
$R | ConvertTo-Json -Depth 6 | Out-File (Join-Path $raiz "mineria\resultados_ssas.json") -Encoding utf8
$txt | Out-File (Join-Path $PSScriptRoot "resultado_consultas_dmx.txt") -Encoding utf8
Write-Output "OK - resultados en mineria\resultados_ssas.json"
