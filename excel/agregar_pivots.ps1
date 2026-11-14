<#
  agregar_pivots.ps1 - Abre el libro con Excel y agrega:
   * Tablas dinamicas OLAP conectadas al cubo SSAS SiniestrosVialesOLAP (hoja Pivot_Cubo_OLAP)
   * Tablas dinamicas sobre la tabla DatosCubo (hoja Pivots_Datos), incluida una con
     "Total acumulado" y "% de enero 2019" (= numero indice base 100).
  Uso: powershell -ExecutionPolicy Bypass -File agregar_pivots.ps1
#>
param([string]$Libro = (Join-Path $PSScriptRoot "TP_Siniestros_Viales_CABA.xlsx"), [string]$Servidor = "localhost\SSAS2019")
$ErrorActionPreference = "Stop"
function Paso($t) { Write-Output ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $t) }
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
try {
  $wb = $xl.Workbooks.Open($Libro)
  if ($null -eq $wb) { $wb = $xl.Workbooks.Item(1) }
  if ($wb.ReadOnly) { throw "El libro se abrio como solo lectura (cerralo si esta abierto en Excel)" }
  Paso ("libro abierto: " + $wb.Name)

  # ---------------------------------------------------------- OLAP (cubo SSAS)
  $cs = "OLEDB;Provider=MSOLAP.8;Integrated Security=SSPI;Persist Security Info=True;Data Source=$Servidor;Initial Catalog=SiniestrosVialesOLAP"
  $conn = $wb.Connections.Add2("Cubo SiniestrosVialesOLAP", "Cubo OLAP SSAS - Siniestros Viales CABA", $cs, "Siniestros Viales", 1)
  $conn.Refresh()
  $ws = $wb.Worksheets.Item("Pivot_Cubo_OLAP")

  $ws.Range("A4").Value2 = "1) Siniestros por año (desplegable a semestre / trimestre / mes / día) y gravedad"
  $pt = $wb.PivotCaches().Create(2, $conn).CreatePivotTable($ws.Range("A6"), "PT_Cubo_Anio_Gravedad")
  $pt.CubeFields.Item("[Tiempo].[Calendario]").Orientation = 1
  $pt.CubeFields.Item("[Gravedad].[Grupo - Gravedad]").Orientation = 2
  $pt.CubeFields.Item("[Measures].[Cantidad Siniestros]").Orientation = 4
  Paso "pivot OLAP 1"

  $ws.Range("H4").Value2 = "2) Medidas calculadas MDX del cubo: acumulado, índice base 2019 = 100, variación interanual"
  $pt2 = $wb.PivotCaches().Create(2, $conn).CreatePivotTable($ws.Range("H6"), "PT_Cubo_Indices")
  $pt2.CubeFields.Item("[Tiempo].[Calendario]").Orientation = 1
  foreach ($m in "Cantidad Siniestros","Siniestros Acumulados","Indice Anual Base 2019","Variacion Interanual %","Victimas Mortales","% Graves o Mortales") {
    $pt2.CubeFields.Item("[Measures].[$m]").Orientation = 4
  }
  Paso "pivot OLAP 2"

  $ws.Range("A30").Value2 = "3) Zona > Comuna por categoría de vehículo de la víctima"
  $pt3 = $wb.PivotCaches().Create(2, $conn).CreatePivotTable($ws.Range("A32"), "PT_Cubo_Comuna_Vehiculo")
  $pt3.CubeFields.Item("[Comuna].[Zona - Comuna]").Orientation = 1
  $pt3.CubeFields.Item("[Vehiculo Victima].[Categoria - Vehiculo]").Orientation = 2
  $pt3.CubeFields.Item("[Measures].[Cantidad Siniestros]").Orientation = 4
  Paso "pivot OLAP 3"

  $ws.Range("A58").Value2 = "4) Letalidad (fallecidos / víctimas) por rango etario y sexo"
  $pt4 = $wb.PivotCaches().Create(2, $conn).CreatePivotTable($ws.Range("A60"), "PT_Cubo_Victimas")
  $pt4.CubeFields.Item("[Rango Etario].[Rango Etario]").Orientation = 1
  $pt4.CubeFields.Item("[Sexo].[Sexo]").Orientation = 2
  $pt4.CubeFields.Item("[Measures].[Letalidad %]").Orientation = 4
  Paso "pivot OLAP 4"

  # ---------------------------------------------------------- Pivots sobre la tabla DatosCubo
  $wd = $wb.Worksheets.Item("Pivots_Datos")
  $pcD = $wb.PivotCaches().Create(1, "DatosCubo")
  $wd.Range("A4").Value2 = "1) Siniestros por año y gravedad"
  $p1 = $pcD.CreatePivotTable($wd.Range("A6"), "PT_Anio_Gravedad")
  $p1.PivotFields("Año").Orientation = 1
  $p1.PivotFields("Gravedad").Orientation = 2
  $f = $p1.AddDataField($p1.PivotFields("CantSiniestros"), "Siniestros", -4157); $f.NumberFormat = "#,##0"
  Paso "pivot datos 1"

  $wd.Range("H4").Value2 = "2) Serie mensual: valor, acumulado (Total en) e índice base 100 (100% = enero 2019)"
  $p2 = $pcD.CreatePivotTable($wd.Range("H6"), "PT_Mes_Indice")
  $p2.PivotFields("AnioMes").Orientation = 1
  $a = $p2.AddDataField($p2.PivotFields("CantSiniestros"), "Siniestros del mes", -4157); $a.NumberFormat = "#,##0"
  $b = $p2.AddDataField($p2.PivotFields("CantSiniestros"), "Acumulado", -4157)
  $b.Calculation = 5; $b.BaseField = "AnioMes"; $b.NumberFormat = "#,##0"
  $c = $p2.AddDataField($p2.PivotFields("CantSiniestros"), "Indice base 100 (% de ene-2019)", -4157)
  $c.Calculation = 3; $c.BaseField = "AnioMes"; $c.BaseItem = "2019-01"; $c.NumberFormat = "0.00%"
  Paso "pivot datos 2"

  $wd.Range("A20").Value2 = "3) Víctimas fatales por comuna y categoría de vehículo de la víctima"
  $p3 = $pcD.CreatePivotTable($wd.Range("A22"), "PT_Comuna_Vehiculo")
  $p3.PivotFields("Comuna").Orientation = 1
  $p3.PivotFields("CategoriaVehiculoVictima").Orientation = 2
  $g = $p3.AddDataField($p3.PivotFields("VictimasMortales"), "Víctimas fatales", -4157); $g.NumberFormat = "#,##0"
  Paso "pivot datos 3"

  $sh = $wd.Shapes.AddChart2(297, 52, 900, 60, 560, 300)   # columnas apiladas
  $sh.Chart.SetSourceData($p1.TableRange1)
  $sh.Chart.HasTitle = $true; $sh.Chart.ChartTitle.Text = "Siniestros por año y gravedad (gráfico dinámico)"
  Paso "grafico dinamico"

  $xl.CalculateFull()
  $wb.Worksheets.Item("Portada").Activate()
  $wb.Save()
  Paso "guardado"

  $vals = $pt2.TableRange1.Value2
  for ($i = 1; $i -le [Math]::Min(10, $vals.GetLength(0)); $i++) {
    $fila = @(); for ($j = 1; $j -le $vals.GetLength(1); $j++) { $fila += $vals[$i, $j] }; Write-Output ($fila -join " | ")
  }
  $v2 = $p2.TableRange1.Value2
  for ($i = 1; $i -le 5; $i++) { $fila = @(); for ($j = 1; $j -le $v2.GetLength(1); $j++) { $fila += $v2[$i, $j] }; Write-Output ($fila -join " | ") }
  $wb.Close($true)
} catch {
  Write-Output ("ERROR: " + $_.Exception.Message + " (linea " + $_.InvocationInfo.ScriptLineNumber + ")")
  try { $wb.Close($false) } catch {}
} finally {
  try { $xl.Quit() } catch {}
  [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
}
