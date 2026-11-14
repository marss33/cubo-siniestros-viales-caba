<#
  desplegar_cubo.ps1 - Crea, despliega y procesa el cubo OLAP multidimensional
  "SiniestrosVialesOLAP" en SQL Server Analysis Services usando AMO.
  Requiere: servicio MSSQLServerOLAPService y MSSQLSERVER iniciados, DW SiniestrosVialesDW cargado.
  Uso:  powershell -ExecutionPolicy Bypass -File desplegar_cubo.ps1 [-Servidor localhost]
  Genera ademas SiniestrosVialesOLAP.xmla (script de la base) para importarlo en Visual Studio.
#>
param([string]$Servidor = "localhost\SSAS2019", [string]$ServidorSQL = "localhost")
$ErrorActionPreference = "Stop"

$candidatos = @(
  "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\SSAS",
  "C:\Program Files\Microsoft SQL Server\170\DTS\Binn"
)
$dir = $candidatos | Where-Object { Test-Path (Join-Path $_ "Microsoft.AnalysisServices.dll") } | Select-Object -First 1
[void][Reflection.Assembly]::LoadFrom((Join-Path $dir "Microsoft.AnalysisServices.Core.dll"))
[void][Reflection.Assembly]::LoadFrom((Join-Path $dir "Microsoft.AnalysisServices.dll"))
Write-Host "AMO cargado desde $dir"

$NS = "Microsoft.AnalysisServices"
$srv = New-Object "$NS.Server"
$srv.Connect($Servidor)
$nombreDB = "SiniestrosVialesOLAP"
$old = $srv.Databases.FindByName($nombreDB)
if ($old) { $old.Drop() }
$db = $srv.Databases.Add($nombreDB)
$db.Update()

# ---------------------------------------------------------------- Origen de datos
$ds = New-Object "$NS.RelationalDataSource" ("DS SiniestrosVialesDW", "DS SiniestrosVialesDW")
$ds.ConnectionString = "Provider=MSOLEDBSQL.1;Data Source=$ServidorSQL;Integrated Security=SSPI;Initial Catalog=SiniestrosVialesDW;TrustServerCertificate=True"
$ds.ImpersonationInfo = New-Object "$NS.ImpersonationInfo" ([Microsoft.AnalysisServices.ImpersonationMode]::ImpersonateServiceAccount)
[void]$db.DataSources.Add($ds)
$ds.Update()

# ---------------------------------------------------------------- Vista de origen de datos (DSV)
$dsv = New-Object "$NS.DataSourceView" ("DSV SiniestrosVialesDW", "DSV SiniestrosVialesDW")
$dsv.DataSourceID = $ds.ID
$dsv.Schema = New-Object System.Data.DataSet ("DSV")
$cnn = New-Object System.Data.SqlClient.SqlConnection ("Data Source=$ServidorSQL;Initial Catalog=SiniestrosVialesDW;Integrated Security=SSPI;TrustServerCertificate=True")
$cnn.Open()
$tablas = "DimTiempo","DimHora","DimComuna","DimTipoVia","DimVehiculo","DimGravedad","DimSexo","DimRangoEtario","DimRolVictima","FactSiniestro","FactVictima"
foreach ($t in $tablas) {
  $da = New-Object System.Data.SqlClient.SqlDataAdapter ("SELECT * FROM dbo.[$t]", $cnn)
  [void]$da.FillSchema($dsv.Schema, [System.Data.SchemaType]::Mapped, "dbo_$t")
  $dt = $dsv.Schema.Tables["dbo_$t"]
  $dt.ExtendedProperties.Add("TableType", "Table")
  $dt.ExtendedProperties.Add("DbSchemaName", "dbo")
  $dt.ExtendedProperties.Add("DbTableName", $t)
  $dt.ExtendedProperties.Add("FriendlyName", $t)
}
# Vistas minables (sql/02_vistas_minables.sql) para las estructuras de mineria de datos
foreach ($t in "vmin_Siniestros","vmin_Victimas","vmin_SerieMensual","vmin_PerfilComunas") {
  $da = New-Object System.Data.SqlClient.SqlDataAdapter ("SELECT * FROM dbo.[$t]", $cnn)
  [void]$da.FillSchema($dsv.Schema, [System.Data.SchemaType]::Mapped, "dbo_$t")
  $dt = $dsv.Schema.Tables["dbo_$t"]
  $dt.ExtendedProperties.Add("TableType", "View")
  $dt.ExtendedProperties.Add("DbSchemaName", "dbo")
  $dt.ExtendedProperties.Add("DbTableName", $t)
  $dt.ExtendedProperties.Add("FriendlyName", $t)
}
$cnn.Close()
function Rel($nombre, $padre, $colPadre, $hijo, $colHijo) {
  $p = $dsv.Schema.Tables["dbo_$padre"].Columns[$colPadre]
  $h = $dsv.Schema.Tables["dbo_$hijo"].Columns[$colHijo]
  [void]$dsv.Schema.Relations.Add($nombre, $p, $h, $false)
}
Rel "FS_Tiempo"    DimTiempo   FechaKey    FactSiniestro FechaKey
Rel "FS_Hora"      DimHora     HoraKey     FactSiniestro HoraKey
Rel "FS_Comuna"    DimComuna   ComunaKey   FactSiniestro ComunaKey
Rel "FS_TipoVia"   DimTipoVia  TipoViaKey  FactSiniestro TipoViaKey
Rel "FS_VehVict"   DimVehiculo VehiculoKey FactSiniestro VehiculoVictimaKey
Rel "FS_Contra"    DimVehiculo VehiculoKey FactSiniestro ContraparteKey
Rel "FS_Gravedad"  DimGravedad GravedadKey FactSiniestro GravedadKey
Rel "FV_Tiempo"    DimTiempo   FechaKey    FactVictima FechaKey
Rel "FV_Hora"      DimHora     HoraKey     FactVictima HoraKey
Rel "FV_Comuna"    DimComuna   ComunaKey   FactVictima ComunaKey
Rel "FV_TipoVia"   DimTipoVia  TipoViaKey  FactVictima TipoViaKey
Rel "FV_Vehiculo"  DimVehiculo VehiculoKey FactVictima VehiculoKey
Rel "FV_Contra"    DimVehiculo VehiculoKey FactVictima ContraparteKey
Rel "FV_Gravedad"  DimGravedad GravedadKey FactVictima GravedadKey
Rel "FV_Sexo"      DimSexo     SexoKey     FactVictima SexoKey
Rel "FV_Rango"     DimRangoEtario RangoEtarioKey FactVictima RangoEtarioKey
Rel "FV_Rol"       DimRolVictima  RolKey     FactVictima RolKey
[void]$db.DataSourceViews.Add($dsv)
$dsv.Update()

# ---------------------------------------------------------------- Helpers
function OleTipo($tabla, $col) {
  $c = $dsv.Schema.Tables["dbo_$tabla"].Columns[$col]
  switch ($c.DataType.Name) {
    "Int32"   { return [System.Data.OleDb.OleDbType]::Integer }
    "Int16"   { return [System.Data.OleDb.OleDbType]::SmallInt }
    "Byte"    { return [System.Data.OleDb.OleDbType]::UnsignedTinyInt }
    "DateTime"{ return [System.Data.OleDb.OleDbType]::Date }
    "Decimal" { return [System.Data.OleDb.OleDbType]::Numeric }
    "Double"  { return [System.Data.OleDb.OleDbType]::Double }
    default   { return [System.Data.OleDb.OleDbType]::WChar }
  }
}
function DI($tabla, $col) {
  $di = New-Object "$NS.DataItem" ("dbo_$tabla", $col, (OleTipo $tabla $col))
  if ((OleTipo $tabla $col) -eq [System.Data.OleDb.OleDbType]::WChar) { $di.DataSize = 200 }
  return $di
}
function NuevaDim($nombre, $tabla) {
  $d = $db.Dimensions.Add($nombre)
  $d.Source = New-Object "$NS.DataSourceViewBinding" ($dsv.ID)
  $d.UnknownMember = [Microsoft.AnalysisServices.UnknownMemberBehavior]::None
  $d.ErrorConfiguration = New-Object "$NS.ErrorConfiguration"
  $d.ErrorConfiguration.KeyDuplicate = [Microsoft.AnalysisServices.ErrorOption]::ReportAndStop
  $d.Language = 11274  # es-AR
  return $d
}
function Atrib($dim, $tabla, $nombre, $colKey, $colName = $null, [switch]$Key, [switch]$OrdenPorKey) {
  $a = $dim.Attributes.Add($nombre)
  if ($Key) { $a.Usage = [Microsoft.AnalysisServices.AttributeUsage]::Key }
  [void]$a.KeyColumns.Add((DI $tabla $colKey))
  if ($colName) { $a.NameColumn = New-Object "$NS.DataItem" ("dbo_$tabla", $colName, [System.Data.OleDb.OleDbType]::WChar, 200) }
  $a.OrderBy = if ($OrdenPorKey) { [Microsoft.AnalysisServices.OrderBy]::Key } else { [Microsoft.AnalysisServices.OrderBy]::Name }
  return $a
}
function RelAtrib($desde, $hacia) {
  $r = $desde.AttributeRelationships.Add($hacia.ID)
  $r.RelationshipType = [Microsoft.AnalysisServices.RelationshipType]::Rigid   # datos historicos: no cambian
}
function Jerarquia($dim, $nombre, $niveles) {
  $h = $dim.Hierarchies.Add($nombre)
  foreach ($n in $niveles) {
    [void]$h.Levels.Add($n.Name).set_SourceAttributeID($n.ID)
    $n.AttributeHierarchyVisible = $false   # se navega por la jerarquia de usuario
  }
  return $h
}

# ---------------------------------------------------------------- Dimension Tiempo
$dT = NuevaDim "Tiempo" "DimTiempo"
$dT.Type = [Microsoft.AnalysisServices.DimensionType]::Time
$fecha = Atrib $dT DimTiempo "Fecha" FechaKey Fecha -Key -OrdenPorKey
$mes   = Atrib $dT DimTiempo "Mes" AnioMes AnioMesNombre -OrdenPorKey
$trim  = Atrib $dT DimTiempo "Trimestre" TrimestreNombre -OrdenPorKey
$sem   = Atrib $dT DimTiempo "Semestre" SemestreNombre -OrdenPorKey
$anio  = Atrib $dT DimTiempo "Anio" Anio -OrdenPorKey
$mesN  = Atrib $dT DimTiempo "Mes del Anio" MesNumero MesNombre -OrdenPorKey
$dsem  = Atrib $dT DimTiempo "Dia de la Semana" DiaSemanaNumero DiaSemanaNombre -OrdenPorKey
$tdia  = Atrib $dT DimTiempo "Tipo de Dia" TipoDia
$est   = Atrib $dT DimTiempo "Estacion" Estacion
$ctx   = Atrib $dT DimTiempo "Contexto" Contexto
$anio.Type = [Microsoft.AnalysisServices.AttributeType]::Years
$sem.Type = [Microsoft.AnalysisServices.AttributeType]::HalfYears
$trim.Type = [Microsoft.AnalysisServices.AttributeType]::Quarters
$mes.Type = [Microsoft.AnalysisServices.AttributeType]::Months
$fecha.Type = [Microsoft.AnalysisServices.AttributeType]::Date
RelAtrib $fecha $mes; RelAtrib $fecha $mesN; RelAtrib $fecha $dsem; RelAtrib $fecha $tdia; RelAtrib $fecha $est; RelAtrib $fecha $ctx
RelAtrib $mes $trim; RelAtrib $trim $sem; RelAtrib $sem $anio
[void](Jerarquia $dT "Calendario" @($anio, $sem, $trim, $mes, $fecha))

# ---------------------------------------------------------------- Dimension Hora
$dH = NuevaDim "Hora" "DimHora"
$hora = Atrib $dH DimHora "Hora" HoraKey Hora -Key -OrdenPorKey
$fr   = Atrib $dH DimHora "Franja Horaria" FranjaHoraria
$pico = Atrib $dH DimHora "Hora Pico" HoraPico
$luz  = Atrib $dH DimHora "Luz" Luz
RelAtrib $hora $fr; RelAtrib $hora $pico; RelAtrib $hora $luz
[void](Jerarquia $dH "Franja - Hora" @($fr, $hora))

# ---------------------------------------------------------------- Dimension Comuna (Geografia)
$dC = NuevaDim "Comuna" "DimComuna"
$com  = Atrib $dC DimComuna "Comuna" ComunaKey Comuna -Key
$zona = Atrib $dC DimComuna "Zona" Zona
$barr = Atrib $dC DimComuna "Barrios" Barrios
RelAtrib $com $zona; RelAtrib $com $barr
[void](Jerarquia $dC "Zona - Comuna" @($zona, $com))

# ---------------------------------------------------------------- Dimension Tipo de Via
$dV = NuevaDim "Tipo de Via" "DimTipoVia"
$tv  = Atrib $dV DimTipoVia "Tipo de Via" TipoViaKey TipoVia -Key
$ctv = Atrib $dV DimTipoVia "Categoria de Via" CategoriaVia
RelAtrib $tv $ctv
[void](Jerarquia $dV "Categoria - Tipo de Via" @($ctv, $tv))

# ---------------------------------------------------------------- Dimension Vehiculo (rol multiple)
$dVe = NuevaDim "Vehiculo" "DimVehiculo"
$veh = Atrib $dVe DimVehiculo "Vehiculo" VehiculoKey Vehiculo -Key
$cve = Atrib $dVe DimVehiculo "Categoria de Vehiculo" CategoriaVehiculo
RelAtrib $veh $cve
[void](Jerarquia $dVe "Categoria - Vehiculo" @($cve, $veh))

# ---------------------------------------------------------------- Dimension Gravedad
$dG = NuevaDim "Gravedad" "DimGravedad"
$gr  = Atrib $dG DimGravedad "Gravedad" GravedadKey Gravedad -Key -OrdenPorKey
$ggr = Atrib $dG DimGravedad "Grupo Gravedad" GrupoGravedad -OrdenPorKey
RelAtrib $gr $ggr
[void](Jerarquia $dG "Grupo - Gravedad" @($ggr, $gr))

# ---------------------------------------------------------------- Dimensiones de la victima
$dimSexo  = NuevaDim "Sexo" "DimSexo";               [void](Atrib $dimSexo DimSexo "Sexo" SexoKey Sexo -Key)
$dimRango = NuevaDim "Rango Etario" "DimRangoEtario"; [void](Atrib $dimRango DimRangoEtario "Rango Etario" RangoEtarioKey RangoEtario -Key -OrdenPorKey)
$dimRol   = NuevaDim "Rol Victima" "DimRolVictima";  [void](Atrib $dimRol DimRolVictima "Rol" RolKey Rol -Key)

foreach ($d in $db.Dimensions) { $d.Update([Microsoft.AnalysisServices.UpdateOptions]::ExpandFull) }

# ---------------------------------------------------------------- Cubo
$cubo = $db.Cubes.Add("Siniestros Viales")
$cubo.Source = New-Object "$NS.DataSourceViewBinding" ($dsv.ID)
$cubo.StorageMode = [Microsoft.AnalysisServices.StorageMode]::Molap
$cubo.Language = 11274
$cdT  = $cubo.Dimensions.Add($dT.ID)
$cdH  = $cubo.Dimensions.Add($dH.ID)
$cdC  = $cubo.Dimensions.Add($dC.ID)
$cdV  = $cubo.Dimensions.Add($dV.ID)
$cdVV = $cubo.Dimensions.Add($dVe.ID, "Vehiculo Victima", "Vehiculo Victima")
$cdCo = $cubo.Dimensions.Add($dVe.ID, "Contraparte", "Contraparte")
$cdG  = $cubo.Dimensions.Add($dG.ID)
$cdS  = $cubo.Dimensions.Add($dimSexo.ID)
$cdR  = $cubo.Dimensions.Add($dimRango.ID)
$cdRo = $cubo.Dimensions.Add($dimRol.ID)

function Medida($mg, $nombre, $tabla, $col, $fmt = "#,##0") {
  $m = $mg.Measures.Add($nombre)
  $m.AggregateFunction = [Microsoft.AnalysisServices.AggregationFunction]::Sum
  $m.Source = New-Object "$NS.DataItem" ("dbo_$tabla", $col, [System.Data.OleDb.OleDbType]::Integer)
  $m.FormatString = $fmt
  return $m
}
function Vincular($mg, $cubeDim, $tabla, $colFK) {
  $rel = New-Object "$NS.RegularMeasureGroupDimension" ($cubeDim.ID)
  $dimBase = $db.Dimensions[$cubeDim.DimensionID]
  $keyAttr = $dimBase.Attributes | Where-Object { $_.Usage -eq [Microsoft.AnalysisServices.AttributeUsage]::Key }
  $mga = $rel.Attributes.Add($keyAttr.ID)
  $mga.Type = [Microsoft.AnalysisServices.MeasureGroupAttributeType]::Granularity
  [void]$mga.KeyColumns.Add((DI $tabla $colFK))
  [void]$mg.Dimensions.Add($rel)
}

$mgS = $cubo.MeasureGroups.Add("Siniestros")
$mgS.StorageMode = [Microsoft.AnalysisServices.StorageMode]::Molap
[void](Medida $mgS "Cantidad Siniestros" FactSiniestro CantSiniestros)
[void](Medida $mgS "Total Victimas" FactSiniestro TotalVictimas)
[void](Medida $mgS "Victimas Leves" FactSiniestro VictimasLeves)
[void](Medida $mgS "Victimas Graves" FactSiniestro VictimasGraves)
[void](Medida $mgS "Victimas Mortales" FactSiniestro VictimasMortales)
Vincular $mgS $cdT  FactSiniestro FechaKey
Vincular $mgS $cdH  FactSiniestro HoraKey
Vincular $mgS $cdC  FactSiniestro ComunaKey
Vincular $mgS $cdV  FactSiniestro TipoViaKey
Vincular $mgS $cdVV FactSiniestro VehiculoVictimaKey
Vincular $mgS $cdCo FactSiniestro ContraparteKey
Vincular $mgS $cdG  FactSiniestro GravedadKey
$pS = $mgS.Partitions.Add("Siniestros")
$pS.Source = New-Object "$NS.TableBinding" ($ds.ID, "dbo", "FactSiniestro")
$pS.StorageMode = [Microsoft.AnalysisServices.StorageMode]::Molap

$mgV = $cubo.MeasureGroups.Add("Victimas")
$mgV.StorageMode = [Microsoft.AnalysisServices.StorageMode]::Molap
[void](Medida $mgV "Cantidad Victimas" FactVictima CantVictimas)
[void](Medida $mgV "Cantidad Fallecidos" FactVictima CantFallecidos)
Vincular $mgV $cdT  FactVictima FechaKey
Vincular $mgV $cdH  FactVictima HoraKey
Vincular $mgV $cdC  FactVictima ComunaKey
Vincular $mgV $cdV  FactVictima TipoViaKey
Vincular $mgV $cdVV FactVictima VehiculoKey
Vincular $mgV $cdCo FactVictima ContraparteKey
Vincular $mgV $cdG  FactVictima GravedadKey
Vincular $mgV $cdS  FactVictima SexoKey
Vincular $mgV $cdR  FactVictima RangoEtarioKey
Vincular $mgV $cdRo FactVictima RolKey
$pV = $mgV.Partitions.Add("Victimas")
$pV.Source = New-Object "$NS.TableBinding" ($ds.ID, "dbo", "FactVictima")
$pV.StorageMode = [Microsoft.AnalysisServices.StorageMode]::Molap

# ---------------------------------------------------------------- Miembros calculados (MDX)
$mdx = @'
CALCULATE;

CREATE MEMBER CURRENTCUBE.[Measures].[Siniestros Graves o Mortales] AS
    ([Measures].[Cantidad Siniestros], [Gravedad].[Grupo Gravedad].&[Grave o mortal]),
    FORMAT_STRING = "#,##0", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[% Graves o Mortales] AS
    IIF([Measures].[Cantidad Siniestros] = 0, NULL,
        [Measures].[Siniestros Graves o Mortales] / [Measures].[Cantidad Siniestros]),
    FORMAT_STRING = "0.00%", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[Victimas por Siniestro] AS
    IIF([Measures].[Cantidad Siniestros] = 0, NULL, [Measures].[Total Victimas] / [Measures].[Cantidad Siniestros]),
    FORMAT_STRING = "0.000", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[Letalidad %] AS
    IIF([Measures].[Cantidad Victimas] = 0, NULL, [Measures].[Cantidad Fallecidos] / [Measures].[Cantidad Victimas]),
    FORMAT_STRING = "0.00%", VISIBLE = 1;

/* Valor acumulable: suma desde el primer periodo hasta el periodo actual (cualquier nivel del calendario) */
CREATE MEMBER CURRENTCUBE.[Measures].[Siniestros Acumulados] AS
    SUM({NULL : [Tiempo].[Calendario].CurrentMember}, [Measures].[Cantidad Siniestros]),
    FORMAT_STRING = "#,##0", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[Mortales Acumulados] AS
    SUM({NULL : [Tiempo].[Calendario].CurrentMember}, [Measures].[Victimas Mortales]),
    FORMAT_STRING = "#,##0", VISIBLE = 1;

/* Numero indice base 100 = enero 2019 */
CREATE MEMBER CURRENTCUBE.[Measures].[Indice Base 100] AS
    IIF([Tiempo].[Calendario].CurrentMember.Level IS [Tiempo].[Calendario].[Mes],
        [Measures].[Cantidad Siniestros] /
        ([Measures].[Cantidad Siniestros], [Tiempo].[Calendario].[Mes].&[2019-01]) * 100, NULL),
    FORMAT_STRING = "0.00", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[Indice Acumulado Base 100] AS
    IIF([Tiempo].[Calendario].CurrentMember.Level IS [Tiempo].[Calendario].[Mes],
        [Measures].[Siniestros Acumulados] /
        ([Measures].[Cantidad Siniestros], [Tiempo].[Calendario].[Mes].&[2019-01]) * 100, NULL),
    FORMAT_STRING = "0.00", VISIBLE = 1;

/* Indice anual base 2019 = 100 */
CREATE MEMBER CURRENTCUBE.[Measures].[Indice Anual Base 2019] AS
    IIF([Tiempo].[Calendario].CurrentMember.Level IS [Tiempo].[Calendario].[Anio],
        [Measures].[Cantidad Siniestros] /
        ([Measures].[Cantidad Siniestros], [Tiempo].[Calendario].[Anio].&[2019]) * 100, NULL),
    FORMAT_STRING = "0.00", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[Variacion Interanual %] AS
    IIF(([Measures].[Cantidad Siniestros], ParallelPeriod([Tiempo].[Calendario].[Anio], 1, [Tiempo].[Calendario].CurrentMember)) = 0, NULL,
        [Measures].[Cantidad Siniestros] /
        ([Measures].[Cantidad Siniestros], ParallelPeriod([Tiempo].[Calendario].[Anio], 1, [Tiempo].[Calendario].CurrentMember)) - 1),
    FORMAT_STRING = "0.00%", VISIBLE = 1;
'@
$cmd = New-Object "$NS.MdxScript" ("MdxScript", "MdxScript")
$c = New-Object "$NS.Command"
$c.Text = $mdx
[void]$cmd.Commands.Add($c)
[void]$cubo.MdxScripts.Add($cmd)

$cubo.Update([Microsoft.AnalysisServices.UpdateOptions]::ExpandFull)

# ---------------------------------------------------------------- Rol de lectura (Excel / usuarios no administradores)
$usuario = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$rol = $db.Roles.Add("Lectores")
[void]$rol.Members.Add((New-Object "$NS.RoleMember" ($usuario)))
$rol.Update()
$dbp = $db.DatabasePermissions.Add($rol.ID)
$dbp.Read = [Microsoft.AnalysisServices.ReadAccess]::Allowed
$dbp.Update()
$cp = $cubo.CubePermissions.Add($rol.ID)
$cp.Read = [Microsoft.AnalysisServices.ReadAccess]::Allowed
$cp.Update()
Write-Host "Rol Lectores creado para $usuario"
Write-Host "Cubo creado. Procesando (ProcessFull)..."
$db.Process([Microsoft.AnalysisServices.ProcessType]::ProcessFull)
Write-Host "Procesado OK:" $db.Name "- estado:" $cubo.State

# ================================================================ MINERIA DE DATOS (SSAS Data Mining)
# Cada estructura de mineria toma una vista minable del DW (modelo estrella) y contiene uno o mas
# modelos con algoritmos nativos de Microsoft. Se ven en Visual Studio en la carpeta "Estructuras de mineria".
function Columna($ms, $vista, $col, $tipo, $contenido, [switch]$Key) {
  $c = New-Object "$NS.ScalarMiningStructureColumn" ($col, $col)
  $c.Type = $tipo
  $c.Content = $contenido
  if ($Key) { $c.IsKey = $true }
  [void]$c.KeyColumns.Add((DI $vista $col))
  [void]$ms.Columns.Add($c)
}
function Estructura($nombre, $holdout) {
  $ms = New-Object "$NS.MiningStructure" ($nombre, $nombre)
  $ms.Source = New-Object "$NS.DataSourceViewBinding" ($dsv.ID)
  if ($holdout -gt 0) { $ms.HoldoutMaxPercent = $holdout; $ms.HoldoutSeed = 42 }
  [void]$db.MiningStructures.Add($ms)
  return $ms
}
function Modelo($ms, $nombre, $algoritmo, $predict, $quitar = @(), $params = @{}) {
  $mm = $ms.CreateMiningModel($true, $nombre)
  $mm.Algorithm = $algoritmo
  foreach ($q in $quitar) { $c = $mm.Columns.Find($q); if ($c) { $mm.Columns.Remove($c) } }
  foreach ($p in $predict) { $mm.Columns.Find($p).Usage = "Predict" }
  foreach ($k in $params.Keys) { [void]$mm.AlgorithmParameters.Add($k, $params[$k]) }
  return $mm
}
$estructuras = @()
try {
  # ---- 1) Clasificacion y segmentacion de siniestros (vista vmin_Siniestros, 30% de prueba)
  $s1 = Estructura "MS Gravedad Siniestros" 30
  Columna $s1 vmin_Siniestros SiniestroID Text Key -Key
  foreach ($c in "FranjaHoraria","TipoDia","DiaSemana","Estacion","Contexto","Comuna","Zona","TipoVia","VehiculoVictima","Contraparte","Gravedad") { Columna $s1 vmin_Siniestros $c Text Discrete }
  Columna $s1 vmin_Siniestros Hora Long Discrete
  Columna $s1 vmin_Siniestros TotalVictimas Long Discrete
  [void](Modelo $s1 "Arbol de Decision - Gravedad" "Microsoft_Decision_Trees" @("Gravedad"))
  [void](Modelo $s1 "Naive Bayes - Gravedad" "Microsoft_Naive_Bayes" @("Gravedad"))
  [void](Modelo $s1 "Regresion Logistica - Gravedad" "Microsoft_Logistic_Regression" @("Gravedad"))
  [void](Modelo $s1 "Red Neuronal - Gravedad" "Microsoft_Neural_Network" @("Gravedad"))
  [void](Modelo $s1 "Clustering - Siniestros" "Microsoft_Clustering" @("Gravedad") @() @{ CLUSTER_COUNT = 6 })
  $estructuras += $s1

  # ---- 2) Reglas de asociacion (cada siniestro = transaccion, cada atributo = item)
  $s2 = Estructura "MS Asociacion Siniestros" 0
  Columna $s2 vmin_Siniestros SiniestroID Text Key -Key
  foreach ($c in "FranjaHoraria","TipoDia","TipoVia","VehiculoVictima","Contraparte","Zona","Gravedad") { Columna $s2 vmin_Siniestros $c Text Discrete }
  [void](Modelo $s2 "Reglas de Asociacion" "Microsoft_Association_Rules" @("FranjaHoraria","TipoDia","TipoVia","VehiculoVictima","Contraparte","Zona","Gravedad") @() @{ MINIMUM_SUPPORT = 0.002; MINIMUM_PROBABILITY = 0.1; MAXIMUM_ITEMSET_SIZE = 4 })
  $estructuras += $s2

  # ---- 3) Serie de tiempo mensual (vector tiempo + vector dato)
  $s3 = Estructura "MS Serie Mensual" 0
  Columna $s3 vmin_SerieMensual Mes Date "Key Time" -Key
  Columna $s3 vmin_SerieMensual Siniestros Double Continuous
  Columna $s3 vmin_SerieMensual Mortales Double Continuous
  [void](Modelo $s3 "Serie de Tiempo - Siniestros" "Microsoft_Time_Series" @("Siniestros","Mortales") @() @{ PERIODICITY_HINT = "{12}" })
  $estructuras += $s3

  # ---- 4) Perfil de victima fatal (vista vmin_Victimas, 30% de prueba)
  $s4 = Estructura "MS Victima Fatal" 30
  Columna $s4 vmin_Victimas VictimaID Long Key -Key
  Columna $s4 vmin_Victimas Edad Long Continuous
  Columna $s4 vmin_Victimas Hora Long Discrete
  foreach ($c in "RangoEtario","Sexo","Vehiculo","TipoVia","FranjaHoraria","TipoDia","Zona","Desenlace") { Columna $s4 vmin_Victimas $c Text Discrete }
  [void](Modelo $s4 "Arbol de Decision - Victima Fatal" "Microsoft_Decision_Trees" @("Desenlace"))
  [void](Modelo $s4 "Naive Bayes - Victima Fatal" "Microsoft_Naive_Bayes" @("Desenlace") @("Edad"))
  $estructuras += $s4

  # ---- 5) Segmentacion de comunas (1 fila = 1 comuna)
  $s5 = Estructura "MS Perfil Comunas" 0
  Columna $s5 vmin_PerfilComunas Comuna Text Key -Key
  Columna $s5 vmin_PerfilComunas Zona Text Discrete
  foreach ($c in "SiniestrosAnuales","PctMoto","PctPeaton","PctBicicleta","PctNocturno","PctFinDeSemana","PctViaRapida","PctTransportePesado","PctGraveMortal") { Columna $s5 vmin_PerfilComunas $c Double Continuous }
  [void](Modelo $s5 "Clustering - Comunas" "Microsoft_Clustering" @() @() @{ CLUSTER_COUNT = 4; MINIMUM_SUPPORT = 1 })
  $estructuras += $s5

  foreach ($ms in $estructuras) {
    $ms.Update([Microsoft.AnalysisServices.UpdateOptions]::ExpandFull)
    $msp = $ms.MiningStructurePermissions.Add($rol.ID)
    $msp.Read = [Microsoft.AnalysisServices.ReadAccess]::Allowed
    $msp.AllowDrillThrough = $true
    $msp.Update()
    foreach ($mm in $ms.MiningModels) {
      $mmp = $mm.MiningModelPermissions.Add($rol.ID)
      $mmp.Read = [Microsoft.AnalysisServices.ReadAccess]::Allowed
      $mmp.AllowBrowsing = $true
      # drillthrough solo en algoritmos que lo soportan (arboles, clustering, asociacion, series de tiempo)
      if ($mm.Algorithm -in "Microsoft_Decision_Trees","Microsoft_Clustering","Microsoft_Association_Rules","Microsoft_Time_Series") {
        $mmp.AllowDrillThrough = $true
        $mm.AllowDrillThrough = $true
        $mm.Update()
      }
      $mmp.Update()
    }
    Write-Host "Procesando estructura de mineria:" $ms.Name
    $ms.Process([Microsoft.AnalysisServices.ProcessType]::ProcessFull)
    Write-Host "   OK -" ($ms.MiningModels | ForEach-Object { $_.Name + " [" + $_.Algorithm + "]" }) -Separator "`n   "
  }
} catch {
  Write-Host "ERROR en mineria de datos:" $_.Exception.Message
  if ($_.Exception.InnerException) { Write-Host "  detalle:" $_.Exception.InnerException.Message }
}

# ---------------------------------------------------------------- Script XMLA (para Visual Studio / SSMS)
$out = Join-Path $PSScriptRoot "SiniestrosVialesOLAP.xmla"
$xw = New-Object System.Xml.XmlTextWriter ($out, [System.Text.Encoding]::UTF8)
$xw.Formatting = [System.Xml.Formatting]::Indented
[Microsoft.AnalysisServices.Scripter]::WriteCreate($xw, $srv, $db, $true, $true)
$xw.Close()
Write-Host "XMLA guardado en $out"
$srv.Disconnect()
