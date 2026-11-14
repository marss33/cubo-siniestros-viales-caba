using System;
using System.Collections.Generic;
using System.Data;
using System.Data.OleDb;
using System.Data.SqlClient;
using System.Linq;
using Microsoft.AnalysisServices;

namespace CuboSiniestrosViales
{
    /// <summary>
    /// Construye la base multidimensional SiniestrosVialesOLAP sobre el Data Warehouse SiniestrosVialesDW
    /// (modelo estrella / constelacion: FactSiniestro y FactVictima + 9 dimensiones).
    /// </summary>
    internal sealed class ConstructorCubo
    {
        private readonly Server _srv;
        private readonly string _servidorSql;
        private Database _db;
        private RelationalDataSource _ds;
        private DataSourceView _dsv;
        private Role _rol;

        public ConstructorCubo(Server srv, string servidorSql)
        {
            _srv = srv;
            _servidorSql = servidorSql;
        }

        public Database Construir()
        {
            Salida.Titulo("1) CONSTRUCCION DEL CUBO OLAP");
            CrearBase();
            CrearOrigenDeDatos();
            CrearVistaOrigenDeDatos();
            var dims = CrearDimensiones();
            var cubo = CrearCubo(dims);
            CrearRolLectura(cubo);
            Salida.ConProgreso("Procesando el cubo (ProcessFull, almacenamiento MOLAP)", () => _db.Process(ProcessType.ProcessFull));
            _db.Refresh();
            Salida.Linea($"Cubo '{cubo.Name}' procesado. Estado: {cubo.State}. Dimensiones: {_db.Dimensions.Count}. Grupos de medida: {cubo.MeasureGroups.Count}");
            return _db;
        }

        // ------------------------------------------------------------------ base, origen de datos y DSV
        private void CrearBase()
        {
            var vieja = _srv.Databases.FindByName(Configuracion.BaseOlap);
            if (vieja != null) { vieja.Drop(); Salida.Linea("Base anterior eliminada."); }
            _db = _srv.Databases.Add(Configuracion.BaseOlap);
            _db.Language = Configuracion.IdiomaEsAr;
            _db.Update();
            Salida.Linea($"Base '{_db.Name}' creada.");
        }

        private void CrearOrigenDeDatos()
        {
            _ds = new RelationalDataSource("DS SiniestrosVialesDW", "DS SiniestrosVialesDW")
            {
                ConnectionString = $"Provider=MSOLEDBSQL.1;Data Source={_servidorSql};Integrated Security=SSPI;" +
                                   $"Initial Catalog={Configuracion.BaseDw};TrustServerCertificate=True",
                ImpersonationInfo = new ImpersonationInfo(ImpersonationMode.ImpersonateServiceAccount)
            };
            _db.DataSources.Add(_ds);
            _ds.Update();
            Salida.Linea("Origen de datos 'DS SiniestrosVialesDW' (SQL Server, proveedor MSOLEDBSQL) creado.");
        }

        private static readonly string[] TablasEstrella =
        {
            "DimTiempo", "DimHora", "DimComuna", "DimTipoVia", "DimVehiculo", "DimGravedad",
            "DimSexo", "DimRangoEtario", "DimRolVictima", "FactSiniestro", "FactVictima"
        };
        internal static readonly string[] VistasMinables =
        {
            "vmin_Siniestros", "vmin_Victimas", "vmin_SerieMensual", "vmin_PerfilComunas"
        };

        private void CrearVistaOrigenDeDatos()
        {
            _dsv = new DataSourceView("DSV SiniestrosVialesDW", "DSV SiniestrosVialesDW")
            {
                DataSourceID = _ds.ID,
                Schema = new DataSet("DSV")
            };
            string cs = $"Data Source={_servidorSql};Initial Catalog={Configuracion.BaseDw};Integrated Security=SSPI;TrustServerCertificate=True";
            using (var cn = new SqlConnection(cs))
            {
                cn.Open();
                foreach (var t in TablasEstrella) AgregarTabla(cn, t, "Table");
                foreach (var v in VistasMinables) AgregarTabla(cn, v, "View");
            }
            // Relaciones del modelo estrella: cada clave foranea de un hecho apunta a la PK de su dimension
            Rel("DimTiempo", "FechaKey", "FactSiniestro", "FechaKey");
            Rel("DimHora", "HoraKey", "FactSiniestro", "HoraKey");
            Rel("DimComuna", "ComunaKey", "FactSiniestro", "ComunaKey");
            Rel("DimTipoVia", "TipoViaKey", "FactSiniestro", "TipoViaKey");
            Rel("DimVehiculo", "VehiculoKey", "FactSiniestro", "VehiculoVictimaKey");
            Rel("DimVehiculo", "VehiculoKey", "FactSiniestro", "ContraparteKey");
            Rel("DimGravedad", "GravedadKey", "FactSiniestro", "GravedadKey");
            Rel("DimTiempo", "FechaKey", "FactVictima", "FechaKey");
            Rel("DimHora", "HoraKey", "FactVictima", "HoraKey");
            Rel("DimComuna", "ComunaKey", "FactVictima", "ComunaKey");
            Rel("DimTipoVia", "TipoViaKey", "FactVictima", "TipoViaKey");
            Rel("DimVehiculo", "VehiculoKey", "FactVictima", "VehiculoKey");
            Rel("DimVehiculo", "VehiculoKey", "FactVictima", "ContraparteKey");
            Rel("DimGravedad", "GravedadKey", "FactVictima", "GravedadKey");
            Rel("DimSexo", "SexoKey", "FactVictima", "SexoKey");
            Rel("DimRangoEtario", "RangoEtarioKey", "FactVictima", "RangoEtarioKey");
            Rel("DimRolVictima", "RolKey", "FactVictima", "RolKey");
            _db.DataSourceViews.Add(_dsv);
            _dsv.Update();
            Salida.Linea($"Vista del origen de datos creada: {TablasEstrella.Length} tablas del modelo estrella, " +
                         $"{_dsv.Schema.Relations.Count} relaciones y {VistasMinables.Length} vistas minables.");
        }

        private void AgregarTabla(SqlConnection cn, string tabla, string tipo)
        {
            using (var da = new SqlDataAdapter($"SELECT * FROM dbo.[{tabla}]", cn))
            {
                da.FillSchema(_dsv.Schema, SchemaType.Mapped, "dbo_" + tabla);
            }
            var dt = _dsv.Schema.Tables["dbo_" + tabla];
            dt.ExtendedProperties.Add("TableType", tipo);
            dt.ExtendedProperties.Add("DbSchemaName", "dbo");
            dt.ExtendedProperties.Add("DbTableName", tabla);
            dt.ExtendedProperties.Add("FriendlyName", tabla);
        }

        private void Rel(string padre, string colPadre, string hijo, string colHijo)
        {
            var p = _dsv.Schema.Tables["dbo_" + padre].Columns[colPadre];
            var h = _dsv.Schema.Tables["dbo_" + hijo].Columns[colHijo];
            _dsv.Schema.Relations.Add($"FK_{hijo}_{colHijo}", p, h, false);
        }

        // ------------------------------------------------------------------ helpers de enlace a columnas
        internal static OleDbType TipoOleDb(DataSourceView dsv, string tabla, string columna)
        {
            var t = dsv.Schema.Tables["dbo_" + tabla].Columns[columna].DataType;
            if (t == typeof(int)) return OleDbType.Integer;
            if (t == typeof(short)) return OleDbType.SmallInt;
            if (t == typeof(byte)) return OleDbType.UnsignedTinyInt;
            if (t == typeof(DateTime)) return OleDbType.Date;
            if (t == typeof(decimal)) return OleDbType.Numeric;
            if (t == typeof(double)) return OleDbType.Double;
            return OleDbType.WChar;
        }

        internal static DataItem Columna(DataSourceView dsv, string tabla, string columna)
        {
            var tipo = TipoOleDb(dsv, tabla, columna);
            var di = new DataItem("dbo_" + tabla, columna, tipo);
            if (tipo == OleDbType.WChar) di.DataSize = 200;
            return di;
        }

        // ------------------------------------------------------------------ dimensiones
        private Dimension NuevaDimension(string nombre)
        {
            var d = _db.Dimensions.Add(nombre);
            d.Source = new DataSourceViewBinding(_dsv.ID);
            d.UnknownMember = UnknownMemberBehavior.None;   // todas las dimensiones tienen su miembro "SIN DATO"
            d.ErrorConfiguration = new ErrorConfiguration { KeyDuplicate = ErrorOption.ReportAndStop };
            d.Language = Configuracion.IdiomaEsAr;
            return d;
        }

        private DimensionAttribute Atributo(Dimension d, string tabla, string nombre, string colClave,
                                            string colNombre = null, bool esClave = false, bool ordenPorClave = false)
        {
            var a = d.Attributes.Add(nombre);
            if (esClave) a.Usage = AttributeUsage.Key;
            a.KeyColumns.Add(Columna(_dsv, tabla, colClave));
            if (colNombre != null) a.NameColumn = new DataItem("dbo_" + tabla, colNombre, OleDbType.WChar, 200);
            a.OrderBy = ordenPorClave ? OrderBy.Key : OrderBy.Name;
            return a;
        }

        private static void Relacion(DimensionAttribute desde, DimensionAttribute hacia)
        {
            var r = desde.AttributeRelationships.Add(hacia.ID);
            r.RelationshipType = RelationshipType.Rigid;   // datos historicos: las relaciones no cambian
        }

        private static void Jerarquia(Dimension d, string nombre, params DimensionAttribute[] niveles)
        {
            var h = d.Hierarchies.Add(nombre);
            foreach (var n in niveles)
            {
                h.Levels.Add(n.Name).SourceAttributeID = n.ID;
                n.AttributeHierarchyVisible = false;   // se navega por la jerarquia de usuario
            }
        }

        private Dictionary<string, Dimension> CrearDimensiones()
        {
            var r = new Dictionary<string, Dimension>();

            // Tiempo: Anio > Semestre > Trimestre > Mes > Fecha
            var t = NuevaDimension("Tiempo");
            t.Type = DimensionType.Time;
            var fecha = Atributo(t, "DimTiempo", "Fecha", "FechaKey", "Fecha", esClave: true, ordenPorClave: true);
            var mes = Atributo(t, "DimTiempo", "Mes", "AnioMes", "AnioMesNombre", ordenPorClave: true);
            var trim = Atributo(t, "DimTiempo", "Trimestre", "TrimestreNombre", ordenPorClave: true);
            var sem = Atributo(t, "DimTiempo", "Semestre", "SemestreNombre", ordenPorClave: true);
            var anio = Atributo(t, "DimTiempo", "Anio", "Anio", ordenPorClave: true);
            var mesAnio = Atributo(t, "DimTiempo", "Mes del Anio", "MesNumero", "MesNombre", ordenPorClave: true);
            var diaSem = Atributo(t, "DimTiempo", "Dia de la Semana", "DiaSemanaNumero", "DiaSemanaNombre", ordenPorClave: true);
            var tipoDia = Atributo(t, "DimTiempo", "Tipo de Dia", "TipoDia");
            var estacion = Atributo(t, "DimTiempo", "Estacion", "Estacion");
            var contexto = Atributo(t, "DimTiempo", "Contexto", "Contexto");
            anio.Type = AttributeType.Years; sem.Type = AttributeType.HalfYears; trim.Type = AttributeType.Quarters;
            mes.Type = AttributeType.Months; fecha.Type = AttributeType.Date;
            foreach (var a in new[] { mes, mesAnio, diaSem, tipoDia, estacion, contexto }) Relacion(fecha, a);
            Relacion(mes, trim); Relacion(trim, sem); Relacion(sem, anio);
            Jerarquia(t, "Calendario", anio, sem, trim, mes, fecha);
            r["Tiempo"] = t;

            // Hora: Franja horaria > Hora
            var h = NuevaDimension("Hora");
            var hora = Atributo(h, "DimHora", "Hora", "HoraKey", "Hora", esClave: true, ordenPorClave: true);
            var franja = Atributo(h, "DimHora", "Franja Horaria", "FranjaHoraria");
            var pico = Atributo(h, "DimHora", "Hora Pico", "HoraPico");
            var luz = Atributo(h, "DimHora", "Luz", "Luz");
            Relacion(hora, franja); Relacion(hora, pico); Relacion(hora, luz);
            Jerarquia(h, "Franja - Hora", franja, hora);
            r["Hora"] = h;

            // Comuna (geografia): Zona > Comuna
            var c = NuevaDimension("Comuna");
            var comuna = Atributo(c, "DimComuna", "Comuna", "ComunaKey", "Comuna", esClave: true);
            var zona = Atributo(c, "DimComuna", "Zona", "Zona");
            var barrios = Atributo(c, "DimComuna", "Barrios", "Barrios");
            Relacion(comuna, zona); Relacion(comuna, barrios);
            Jerarquia(c, "Zona - Comuna", zona, comuna);
            r["Comuna"] = c;

            // Tipo de via: Categoria > Tipo
            var v = NuevaDimension("Tipo de Via");
            var tipoVia = Atributo(v, "DimTipoVia", "Tipo de Via", "TipoViaKey", "TipoVia", esClave: true);
            var catVia = Atributo(v, "DimTipoVia", "Categoria de Via", "CategoriaVia");
            Relacion(tipoVia, catVia);
            Jerarquia(v, "Categoria - Tipo de Via", catVia, tipoVia);
            r["Tipo de Via"] = v;

            // Vehiculo (dimension de rol multiple: victima y contraparte)
            var ve = NuevaDimension("Vehiculo");
            var vehiculo = Atributo(ve, "DimVehiculo", "Vehiculo", "VehiculoKey", "Vehiculo", esClave: true);
            var catVeh = Atributo(ve, "DimVehiculo", "Categoria de Vehiculo", "CategoriaVehiculo");
            Relacion(vehiculo, catVeh);
            Jerarquia(ve, "Categoria - Vehiculo", catVeh, vehiculo);
            r["Vehiculo"] = ve;

            // Gravedad: Grupo > Gravedad
            var g = NuevaDimension("Gravedad");
            var grav = Atributo(g, "DimGravedad", "Gravedad", "GravedadKey", "Gravedad", esClave: true, ordenPorClave: true);
            var grupo = Atributo(g, "DimGravedad", "Grupo Gravedad", "GrupoGravedad", ordenPorClave: true);
            Relacion(grav, grupo);
            Jerarquia(g, "Grupo - Gravedad", grupo, grav);
            r["Gravedad"] = g;

            // Dimensiones de la victima
            var sx = NuevaDimension("Sexo"); Atributo(sx, "DimSexo", "Sexo", "SexoKey", "Sexo", esClave: true); r["Sexo"] = sx;
            var re = NuevaDimension("Rango Etario"); Atributo(re, "DimRangoEtario", "Rango Etario", "RangoEtarioKey", "RangoEtario", esClave: true, ordenPorClave: true); r["Rango Etario"] = re;
            var ro = NuevaDimension("Rol Victima"); Atributo(ro, "DimRolVictima", "Rol", "RolKey", "Rol", esClave: true); r["Rol Victima"] = ro;

            foreach (var d in r.Values) d.Update(UpdateOptions.ExpandFull);
            Salida.Linea("Dimensiones creadas: " + string.Join(", ", r.Keys) +
                         " (jerarquias Calendario, Franja-Hora, Zona-Comuna, Categoria-Tipo de Via, Categoria-Vehiculo, Grupo-Gravedad)");
            return r;
        }

        // ------------------------------------------------------------------ cubo
        private Cube CrearCubo(Dictionary<string, Dimension> d)
        {
            var cubo = _db.Cubes.Add(Configuracion.NombreCubo);
            cubo.Source = new DataSourceViewBinding(_dsv.ID);
            cubo.StorageMode = StorageMode.Molap;
            cubo.Language = Configuracion.IdiomaEsAr;

            var cdTiempo = cubo.Dimensions.Add(d["Tiempo"].ID);
            var cdHora = cubo.Dimensions.Add(d["Hora"].ID);
            var cdComuna = cubo.Dimensions.Add(d["Comuna"].ID);
            var cdVia = cubo.Dimensions.Add(d["Tipo de Via"].ID);
            var cdVehVict = cubo.Dimensions.Add(d["Vehiculo"].ID, "Vehiculo Victima", "Vehiculo Victima");   // rol 1
            var cdContra = cubo.Dimensions.Add(d["Vehiculo"].ID, "Contraparte", "Contraparte");                // rol 2
            var cdGrav = cubo.Dimensions.Add(d["Gravedad"].ID);
            var cdSexo = cubo.Dimensions.Add(d["Sexo"].ID);
            var cdRango = cubo.Dimensions.Add(d["Rango Etario"].ID);
            var cdRol = cubo.Dimensions.Add(d["Rol Victima"].ID);

            // Grupo de medida 1: Siniestros (grano: 1 siniestro)
            var mgS = cubo.MeasureGroups.Add("Siniestros");
            mgS.StorageMode = StorageMode.Molap;
            Medida(mgS, "Cantidad Siniestros", "FactSiniestro", "CantSiniestros");
            Medida(mgS, "Total Victimas", "FactSiniestro", "TotalVictimas");
            Medida(mgS, "Victimas Leves", "FactSiniestro", "VictimasLeves");
            Medida(mgS, "Victimas Graves", "FactSiniestro", "VictimasGraves");
            Medida(mgS, "Victimas Mortales", "FactSiniestro", "VictimasMortales");
            Vincular(mgS, cdTiempo, "FactSiniestro", "FechaKey");
            Vincular(mgS, cdHora, "FactSiniestro", "HoraKey");
            Vincular(mgS, cdComuna, "FactSiniestro", "ComunaKey");
            Vincular(mgS, cdVia, "FactSiniestro", "TipoViaKey");
            Vincular(mgS, cdVehVict, "FactSiniestro", "VehiculoVictimaKey");
            Vincular(mgS, cdContra, "FactSiniestro", "ContraparteKey");
            Vincular(mgS, cdGrav, "FactSiniestro", "GravedadKey");
            var pS = mgS.Partitions.Add("Siniestros");
            pS.Source = new TableBinding(_ds.ID, "dbo", "FactSiniestro");
            pS.StorageMode = StorageMode.Molap;

            // Grupo de medida 2: Victimas (grano: 1 victima)
            var mgV = cubo.MeasureGroups.Add("Victimas");
            mgV.StorageMode = StorageMode.Molap;
            Medida(mgV, "Cantidad Victimas", "FactVictima", "CantVictimas");
            Medida(mgV, "Cantidad Fallecidos", "FactVictima", "CantFallecidos");
            Vincular(mgV, cdTiempo, "FactVictima", "FechaKey");
            Vincular(mgV, cdHora, "FactVictima", "HoraKey");
            Vincular(mgV, cdComuna, "FactVictima", "ComunaKey");
            Vincular(mgV, cdVia, "FactVictima", "TipoViaKey");
            Vincular(mgV, cdVehVict, "FactVictima", "VehiculoKey");
            Vincular(mgV, cdContra, "FactVictima", "ContraparteKey");
            Vincular(mgV, cdGrav, "FactVictima", "GravedadKey");
            Vincular(mgV, cdSexo, "FactVictima", "SexoKey");
            Vincular(mgV, cdRango, "FactVictima", "RangoEtarioKey");
            Vincular(mgV, cdRol, "FactVictima", "RolKey");
            var pV = mgV.Partitions.Add("Victimas");
            pV.Source = new TableBinding(_ds.ID, "dbo", "FactVictima");
            pV.StorageMode = StorageMode.Molap;

            // Medidas calculadas (MDX): % graves, letalidad, valor acumulable, numero indice base 100
            var script = new MdxScript("MdxScript", "MdxScript");
            script.Commands.Add(new Command(ScriptMdx));
            cubo.MdxScripts.Add(script);

            cubo.Update(UpdateOptions.ExpandFull);
            Salida.Linea("Cubo creado: grupos de medida Siniestros (5 medidas) y Victimas (2 medidas), 10 dimensiones de cubo " +
                         "(Vehiculo usada 2 veces: Vehiculo Victima y Contraparte) y 10 medidas calculadas MDX.");
            return cubo;
        }

        private static void Medida(MeasureGroup mg, string nombre, string tabla, string columna)
        {
            var m = mg.Measures.Add(nombre);
            m.AggregateFunction = AggregationFunction.Sum;
            m.Source = new DataItem("dbo_" + tabla, columna, OleDbType.Integer);
            m.FormatString = "#,##0";
        }

        private void Vincular(MeasureGroup mg, CubeDimension cd, string tablaHechos, string claveForanea)
        {
            var rel = new RegularMeasureGroupDimension(cd.ID);
            var clave = _db.Dimensions[cd.DimensionID].KeyAttribute;
            var mga = rel.Attributes.Add(clave.ID);
            mga.Type = MeasureGroupAttributeType.Granularity;
            mga.KeyColumns.Add(Columna(_dsv, tablaHechos, claveForanea));
            mg.Dimensions.Add(rel);
        }

        private void CrearRolLectura(Cube cubo)
        {
            _rol = _db.Roles.Add("Lectores");
            _rol.Members.Add(new RoleMember(System.Security.Principal.WindowsIdentity.GetCurrent().Name));
            _rol.Update();
            var dbp = _db.DatabasePermissions.Add(_rol.ID);
            dbp.Read = ReadAccess.Allowed;
            dbp.Update();
            var cp = cubo.CubePermissions.Add(_rol.ID);
            cp.Read = ReadAccess.Allowed;
            cp.Update();
            Salida.Linea($"Rol 'Lectores' (lectura del cubo y la mineria) para {System.Security.Principal.WindowsIdentity.GetCurrent().Name}.");
        }

        private const string ScriptMdx = @"CALCULATE;

CREATE MEMBER CURRENTCUBE.[Measures].[Siniestros Graves o Mortales] AS
    ([Measures].[Cantidad Siniestros], [Gravedad].[Grupo Gravedad].&[Grave o mortal]),
    FORMAT_STRING = ""#,##0"", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[% Graves o Mortales] AS
    IIF([Measures].[Cantidad Siniestros] = 0, NULL,
        [Measures].[Siniestros Graves o Mortales] / [Measures].[Cantidad Siniestros]),
    FORMAT_STRING = ""0.00%"", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[Victimas por Siniestro] AS
    IIF([Measures].[Cantidad Siniestros] = 0, NULL, [Measures].[Total Victimas] / [Measures].[Cantidad Siniestros]),
    FORMAT_STRING = ""0.000"", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[Letalidad %] AS
    IIF([Measures].[Cantidad Victimas] = 0, NULL, [Measures].[Cantidad Fallecidos] / [Measures].[Cantidad Victimas]),
    FORMAT_STRING = ""0.00%"", VISIBLE = 1;

/* Valor acumulable: suma desde el primer periodo hasta el periodo actual */
CREATE MEMBER CURRENTCUBE.[Measures].[Siniestros Acumulados] AS
    SUM({NULL : [Tiempo].[Calendario].CurrentMember}, [Measures].[Cantidad Siniestros]),
    FORMAT_STRING = ""#,##0"", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[Mortales Acumulados] AS
    SUM({NULL : [Tiempo].[Calendario].CurrentMember}, [Measures].[Victimas Mortales]),
    FORMAT_STRING = ""#,##0"", VISIBLE = 1;

/* Numero indice base 100 = enero 2019 */
CREATE MEMBER CURRENTCUBE.[Measures].[Indice Base 100] AS
    IIF([Tiempo].[Calendario].CurrentMember.Level IS [Tiempo].[Calendario].[Mes],
        [Measures].[Cantidad Siniestros] /
        ([Measures].[Cantidad Siniestros], [Tiempo].[Calendario].[Mes].&[2019-01]) * 100, NULL),
    FORMAT_STRING = ""0.00"", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[Indice Acumulado Base 100] AS
    IIF([Tiempo].[Calendario].CurrentMember.Level IS [Tiempo].[Calendario].[Mes],
        [Measures].[Siniestros Acumulados] /
        ([Measures].[Cantidad Siniestros], [Tiempo].[Calendario].[Mes].&[2019-01]) * 100, NULL),
    FORMAT_STRING = ""0.00"", VISIBLE = 1;

/* Indice anual base 2019 = 100 */
CREATE MEMBER CURRENTCUBE.[Measures].[Indice Anual Base 2019] AS
    IIF([Tiempo].[Calendario].CurrentMember.Level IS [Tiempo].[Calendario].[Anio],
        [Measures].[Cantidad Siniestros] /
        ([Measures].[Cantidad Siniestros], [Tiempo].[Calendario].[Anio].&[2019]) * 100, NULL),
    FORMAT_STRING = ""0.00"", VISIBLE = 1;

CREATE MEMBER CURRENTCUBE.[Measures].[Variacion Interanual %] AS
    IIF(([Measures].[Cantidad Siniestros], ParallelPeriod([Tiempo].[Calendario].[Anio], 1, [Tiempo].[Calendario].CurrentMember)) = 0, NULL,
        [Measures].[Cantidad Siniestros] /
        ([Measures].[Cantidad Siniestros], ParallelPeriod([Tiempo].[Calendario].[Anio], 1, [Tiempo].[Calendario].CurrentMember)) - 1),
    FORMAT_STRING = ""0.00%"", VISIBLE = 1;
";
    }
}
