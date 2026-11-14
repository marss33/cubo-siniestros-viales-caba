<#
  consultas_mdx.ps1 - Valida el cubo con consultas MDX (equivalente al Cube Browser).
  Uso: powershell -ExecutionPolicy Bypass -File consultas_mdx.ps1 [-Servidor localhost]
#>
param([string]$Servidor = "localhost\SSAS2019")
$ErrorActionPreference = "Stop"
[void][Reflection.Assembly]::LoadFrom("C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\SSAS\Microsoft.AnalysisServices.AdomdClient.dll")
$cn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection ("Data Source=$Servidor;Catalog=SiniestrosVialesOLAP")
$cn.Open()

$consultas = [ordered]@{
"1. Totales por anio con indice base 2019" = @'
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Total Victimas], [Measures].[Victimas Mortales],
         [Measures].[% Graves o Mortales], [Measures].[Indice Anual Base 2019], [Measures].[Variacion Interanual %] } ON COLUMNS,
       [Tiempo].[Calendario].[Anio].MEMBERS ON ROWS
FROM [Siniestros Viales]
'@
"2. Serie mensual: valor, acumulado e indice base 100 (primeros 14 meses)" = @'
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Siniestros Acumulados],
         [Measures].[Indice Base 100], [Measures].[Indice Acumulado Base 100] } ON COLUMNS,
       HEAD([Tiempo].[Calendario].[Mes].MEMBERS, 14) ON ROWS
FROM [Siniestros Viales]
'@
"3. Ultimos 3 meses (valor acumulado final)" = @'
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Siniestros Acumulados], [Measures].[Indice Base 100],
         [Measures].[Indice Acumulado Base 100] } ON COLUMNS,
       TAIL([Tiempo].[Calendario].[Mes].MEMBERS, 3) ON ROWS
FROM [Siniestros Viales]
'@
"4. Zona > Comuna" = @'
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Victimas Mortales], [Measures].[% Graves o Mortales] } ON COLUMNS,
       NON EMPTY [Comuna].[Zona - Comuna].MEMBERS ON ROWS
FROM [Siniestros Viales]
'@
"5. Vehiculo de la victima x Gravedad" = @'
SELECT [Gravedad].[Gravedad].[Gravedad].MEMBERS * { [Measures].[Cantidad Siniestros] } ON COLUMNS,
       NON EMPTY [Vehiculo Victima].[Vehiculo].[Vehiculo].MEMBERS ON ROWS
FROM [Siniestros Viales]
'@
"6. Letalidad por rango etario y sexo (grupo de medida Victimas)" = @'
SELECT [Sexo].[Sexo].[Sexo].MEMBERS * { [Measures].[Cantidad Victimas], [Measures].[Letalidad %] } ON COLUMNS,
       [Rango Etario].[Rango Etario].[Rango Etario].MEMBERS ON ROWS
FROM [Siniestros Viales]
'@
"7. Franja horaria: fin de semana vs dia habil" = @'
SELECT [Tiempo].[Tipo de Dia].[Tipo de Dia].MEMBERS * { [Measures].[Cantidad Siniestros], [Measures].[% Graves o Mortales] } ON COLUMNS,
       [Hora].[Franja Horaria].[Franja Horaria].MEMBERS ON ROWS
FROM [Siniestros Viales]
'@
}
foreach ($k in $consultas.Keys) {
  Write-Output ""; Write-Output "==== $k"
  $cs = (New-Object Microsoft.AnalysisServices.AdomdClient.AdomdCommand ($consultas[$k], $cn)).ExecuteCellSet()
  $cols = $cs.Axes[0].Positions | ForEach-Object { ($_.Members | ForEach-Object { $_.Caption }) -join " / " }
  Write-Output ("{0,-34}" -f "") + (($cols | ForEach-Object { "{0,22}" -f $_ }) -join "")
  $nc = $cols.Count; $r = 0
  foreach ($p in $cs.Axes[1].Positions) {
    $fila = ("{0,-34}" -f (($p.Members | ForEach-Object { $_.Caption }) -join " / "))
    for ($j = 0; $j -lt $nc; $j++) { $fila += ("{0,22}" -f $cs.Cells[$j, $r].FormattedValue) }
    Write-Output $fila; $r++
  }
}
$cn.Close()
