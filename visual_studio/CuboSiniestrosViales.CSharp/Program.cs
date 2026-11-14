using System;
using System.IO;
using Microsoft.AnalysisServices;

namespace CuboSiniestrosViales
{
    /// <summary>
    /// TP Base de Datos Aplicada - Cubo OLAP y Mineria de Datos de Siniestros Viales (CABA 2019-2025).
    ///
    /// Flujo completo (opcion por defecto "todo"):
    ///   1. Conecta a SQL Server Analysis Services (instancia localhost\SSAS2019).
    ///   2. Crea la base SiniestrosVialesOLAP: origen de datos, vista del origen de datos (modelo estrella),
    ///      9 dimensiones con jerarquias, el cubo "Siniestros Viales" con 2 grupos de medida y medidas MDX.
    ///   3. Crea 5 estructuras de mineria con 10 modelos (algoritmos nativos de Microsoft).
    ///   4. Procesa todo (MOLAP + entrenamiento de los modelos).
    ///   5. Ejecuta consultas MDX (validacion del cubo, indice base 100) y DMX (resultados de mineria).
    ///
    /// Uso:  CuboSiniestrosViales.exe [todo|cubo|mineria|consultas] [servidorOLAP] [servidorSQL]
    /// </summary>
    internal static class Program
    {
        private static int Main(string[] args)
        {
            Console.OutputEncoding = System.Text.Encoding.UTF8;
            bool interactivo = args.Length == 0 && !Console.IsInputRedirected;
            string accion = args.Length > 0 ? args[0].ToLowerInvariant() : (interactivo ? Menu() : "todo");
            if (accion == "salir") return 0;
            string servidorOlap = args.Length > 1 ? args[1] : Configuracion.ServidorOlap;
            string servidorSql = args.Length > 2 ? args[2] : Configuracion.ServidorSql;

            int codigo = Ejecutar(accion, servidorOlap, servidorSql);
            if (interactivo)
            {
                Console.WriteLine();
                Console.WriteLine("Resultados guardados en: " + Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "resultados_ejecucion.txt"));
                Console.Write("Presione una tecla para cerrar...");
                Console.ReadKey(true);
            }
            return codigo;
        }

        private static string Menu()
        {
            Console.WriteLine("====================================================================================");
            Console.WriteLine(" CUBO OLAP Y MINERIA DE DATOS - SINIESTROS VIALES CABA 2019-2025  (C# + AMO/ADOMD)");
            Console.WriteLine("====================================================================================");
            Console.WriteLine($" Servidor OLAP: {Configuracion.ServidorOlap}   Base: {Configuracion.BaseOlap}");
            Console.WriteLine();
            Console.WriteLine("  1) TODO: construir el cubo + entrenar la mineria + consultas MDX/DMX   (~12 minutos)");
            Console.WriteLine("  2) Solo CONSULTAS MDX (cubo) y DMX (mineria) sobre lo ya creado      (segundos)");
            Console.WriteLine("  3) Solo construir y procesar el CUBO                                   (~1 minuto)");
            Console.WriteLine("  4) Solo construir y entrenar la MINERIA sobre el cubo existente        (~11 minutos)");
            Console.WriteLine("  0) Salir");
            Console.WriteLine();
            while (true)
            {
                Console.Write("Opcion: ");
                switch ((Console.ReadLine() ?? "").Trim())
                {
                    case "1": return "todo";
                    case "2": return "consultas";
                    case "3": return "cubo";
                    case "4": return "mineria";
                    case "0": return "salir";
                }
            }
        }

        private static int Ejecutar(string accion, string servidorOlap, string servidorSql)
        {
            Salida.Iniciar(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "resultados_ejecucion.txt"));
            Salida.Titulo("CUBO OLAP Y MINERIA DE DATOS - SINIESTROS VIALES CABA 2019-2025");
            Salida.Linea($"Servidor OLAP: {servidorOlap}   |   Data Warehouse: {servidorSql} / {Configuracion.BaseDw}");

            try
            {
                if (accion == "todo" || accion == "cubo" || accion == "mineria")
                {
                    using (var srv = new Server())
                    {
                        srv.Connect(servidorOlap);
                        Salida.Linea($"Conectado a Analysis Services {srv.Version} ({srv.Edition})");

                        Database db;
                        if (accion == "mineria")
                        {
                            db = srv.Databases.FindByName(Configuracion.BaseOlap)
                                 ?? throw new InvalidOperationException("Primero hay que crear el cubo (accion 'cubo').");
                        }
                        else
                        {
                            var cubo = new ConstructorCubo(srv, servidorSql);
                            db = cubo.Construir();
                        }

                        if (accion == "todo" || accion == "mineria")
                        {
                            var mineria = new ConstructorMineria(db);
                            mineria.Construir();
                        }

                        string xmla = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "SiniestrosVialesOLAP.xmla");
                        ExportarXmla(srv, db, xmla);
                        Salida.Linea($"Definicion completa exportada a {xmla}");
                    }
                }

                if (accion == "todo" || accion == "consultas")
                {
                    ConsultasMdx.Ejecutar(servidorOlap);
                    if (HayMineria(servidorOlap)) ConsultasDmx.Ejecutar(servidorOlap);
                    else Salida.Linea("\nAVISO: la base no tiene modelos de mineria. Ejecute la opcion 1 (todo) o 4 (mineria).");
                }

                Salida.Titulo("FIN - todo OK");
                return 0;
            }
            catch (Exception ex)
            {
                Salida.Linea("ERROR: " + ex.Message);
                if (ex.InnerException != null) Salida.Linea("  detalle: " + ex.InnerException.Message);
                return 1;
            }
            finally
            {
                Salida.Cerrar();
            }
        }

        private static bool HayMineria(string servidorOlap)
        {
            using (var srv = new Server())
            {
                srv.Connect(servidorOlap);
                var db = srv.Databases.FindByName(Configuracion.BaseOlap);
                return db != null && db.MiningStructures.Count > 0;
            }
        }

        private static void ExportarXmla(Server srv, Database db, string ruta)
        {
            using (var xw = new System.Xml.XmlTextWriter(ruta, System.Text.Encoding.UTF8) { Formatting = System.Xml.Formatting.Indented })
            {
                Scripter.WriteCreate(xw, srv, db, true, true);
            }
        }
    }

    /// <summary>Parametros de conexion del proyecto.</summary>
    internal static class Configuracion
    {
        public const string ServidorOlap = @"localhost\SSAS2019";
        public const string ServidorSql = "localhost";
        public const string BaseDw = "SiniestrosVialesDW";
        public const string BaseOlap = "SiniestrosVialesOLAP";
        public const string NombreCubo = "Siniestros Viales";
        public const int IdiomaEsAr = 11274;
    }

    /// <summary>Escribe en consola y en un archivo de resultados al mismo tiempo.</summary>
    internal static class Salida
    {
        private static StreamWriter _archivo;
        public static void Iniciar(string ruta) { _archivo = new StreamWriter(ruta, false, new System.Text.UTF8Encoding(true)) { AutoFlush = true }; }
        public static void Cerrar() { _archivo?.Dispose(); }
        public static void Linea(string texto = "") { Console.WriteLine(texto); _archivo?.WriteLine(texto); }
        public static void Titulo(string texto)
        {
            Linea(); Linea(new string('=', 100)); Linea(texto); Linea(new string('=', 100));
        }

        /// <summary>Ejecuta una tarea larga mostrando el tiempo transcurrido cada 10 segundos.</summary>
        public static void ConProgreso(string tarea, System.Action accion)
        {
            var reloj = System.Diagnostics.Stopwatch.StartNew();
            using (var timer = new System.Threading.Timer(_ =>
                       Console.Write($"\r   {tarea}... {reloj.Elapsed:mm\\:ss} transcurridos   "), null, 0, 10000))
            {
                accion();
            }
            Console.Write("\r" + new string(' ', 90) + "\r");
            Linea($"   {tarea}: listo en {reloj.Elapsed:mm\\:ss}");
        }
    }
}
