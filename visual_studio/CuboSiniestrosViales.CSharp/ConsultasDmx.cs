using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Microsoft.AnalysisServices.AdomdClient;

namespace CuboSiniestrosViales
{
    /// <summary>
    /// Consultas DMX (Data Mining Extensions) sobre los modelos entrenados: precision, contenido de los modelos
    /// (reglas del arbol, clusters, reglas de asociacion), pronostico de la serie de tiempo y predicciones.
    /// </summary>
    internal static class ConsultasDmx
    {
        private static readonly CultureInfo Es = new CultureInfo("es-AR");

        public static void Ejecutar(string servidor)
        {
            Salida.Titulo("4) CONSULTAS DMX SOBRE LOS MODELOS DE MINERIA");
            using (var cn = new AdomdConnection($"Data Source={servidor};Catalog={Configuracion.BaseOlap}"))
            {
                cn.Open();
                Precision(cn);
                ArbolDeDecision(cn);
                Escenarios(cn);
                Clustering(cn);
                Asociacion(cn);
                SerieDeTiempo(cn);
                VictimaFatal(cn);
                ClusteringComunas(cn);
            }
        }

        private static List<Dictionary<string, object>> Leer(AdomdConnection cn, string dmx)
        {
            var filas = new List<Dictionary<string, object>>();
            using (var rd = new AdomdCommand(dmx, cn) { CommandTimeout = 0 }.ExecuteReader())
            {
                while (rd.Read())
                {
                    var f = new Dictionary<string, object>();
                    for (int i = 0; i < rd.FieldCount; i++)
                    {
                        string n = rd.GetName(i);
                        n = n.Substring(n.LastIndexOf('.') + 1).Trim('[', ']');
                        f[n] = rd.IsDBNull(i) ? null : rd.GetValue(i);
                    }
                    filas.Add(f);
                }
            }
            return filas;
        }

        private static double D(object o) => o == null ? 0 : Convert.ToDouble(o, CultureInfo.InvariantCulture);
        private static string Pct(object o) => (D(o) * 100).ToString("0.0", Es) + "%";

        // ------------------------------------------------------------------ 1. precision (casos de prueba)
        private static void Precision(AdomdConnection cn)
        {
            Salida.Linea(); Salida.Linea("--- Precisión de los clasificadores sobre el 30% de prueba (SystemGetAccuracyResults)");
            var r = Leer(cn, @"CALL SystemGetAccuracyResults([MS Gravedad Siniestros], [Arbol de Decision - Gravedad], [Naive Bayes - Gravedad],
                                 [Regresion Logistica - Gravedad], [Red Neuronal - Gravedad], 2, 'Gravedad', 'GRAVE O MORTAL')");
            foreach (var g in r.GroupBy(x => x["ModelName"]?.ToString()))
            {
                string Val(string medida) => g.Where(x => x["Measure"]?.ToString() == medida).Select(x => D(x["Value"])).FirstOrDefault().ToString("0.####", Es);
                Salida.Linea($"{g.Key,-34} TP={Val("True Positive"),-6} FP={Val("False Positive"),-6} TN={Val("True Negative"),-7} FN={Val("False Negative"),-6} LogScore={Val("Log Score")}");
            }
            Salida.Linea("Nota: con umbral 50% la clase minoritaria (7% de graves) casi no se predice; los modelos se usan por su probabilidad (PredictProbability).");
        }

        // ------------------------------------------------------------------ 2. contenido del arbol
        private static void ArbolDeDecision(AdomdConnection cn)
        {
            Salida.Linea(); Salida.Linea("--- Árbol de decisión: hojas con mayor probabilidad de siniestro GRAVE O MORTAL");
            var hojas = Leer(cn, @"SELECT FLATTENED NODE_DESCRIPTION, NODE_SUPPORT,
                                     (SELECT ATTRIBUTE_VALUE, [PROBABILITY] FROM NODE_DISTRIBUTION) AS D
                                   FROM [Arbol de Decision - Gravedad].CONTENT WHERE NODE_TYPE = 4");
            foreach (var h in hojas.Where(x => x["ATTRIBUTE_VALUE"]?.ToString() == "GRAVE O MORTAL")
                                   .OrderByDescending(x => D(x["PROBABILITY"])).Take(8))
                Salida.Linea($"  {Pct(h["PROBABILITY"]),7}  ({h["NODE_SUPPORT"],5} casos)  {h["NODE_DESCRIPTION"]}");
        }

        // ------------------------------------------------------------------ 3. predicciones de escenarios
        private static void Escenarios(AdomdConnection cn)
        {
            Salida.Linea(); Salida.Linea("--- Predicción de escenarios (consulta DMX singleton con PREDICTION JOIN)");
            var escenarios = new (string nombre, string valores)[]
            {
                ("Peatón vs colectivo, avenida, madrugada", "'PEATON' AS [VehiculoVictima], 'TRANSPORTE PUBLICO' AS [Contraparte], 'AVENIDA' AS [TipoVia], '1. Madrugada (00-05)' AS [FranjaHoraria]"),
                ("Moto vs objeto fijo, fin de semana, madrugada", "'MOTO' AS [VehiculoVictima], 'OBJETO FIJO' AS [Contraparte], 'Fin de semana' AS [TipoDia], '1. Madrugada (00-05)' AS [FranjaHoraria]"),
                ("Moto vs auto, Gral. Paz, noche", "'MOTO' AS [VehiculoVictima], 'AUTO' AS [Contraparte], 'AV. GRAL. PAZ' AS [TipoVia], '4. Noche (18-23)' AS [FranjaHoraria]"),
                ("Ciclista vs auto, calle, tarde hábil", "'BICICLETA' AS [VehiculoVictima], 'AUTO' AS [Contraparte], 'CALLE' AS [TipoVia], '3. Tarde (12-17)' AS [FranjaHoraria], 'Dia habil' AS [TipoDia]"),
                ("Auto vs auto, avenida, tarde hábil", "'AUTO' AS [VehiculoVictima], 'AUTO' AS [Contraparte], 'AVENIDA' AS [TipoVia], '3. Tarde (12-17)' AS [FranjaHoraria], 'Dia habil' AS [TipoDia]"),
            };
            var modelos = new[] { "Arbol de Decision - Gravedad", "Naive Bayes - Gravedad", "Regresion Logistica - Gravedad", "Red Neuronal - Gravedad" };
            Salida.Linea("".PadRight(48) + string.Concat(modelos.Select(m => m.Replace(" - Gravedad", "").PadLeft(21))));
            foreach (var (nombre, valores) in escenarios)
            {
                var linea = nombre.PadRight(48);
                foreach (var m in modelos)
                {
                    var r = Leer(cn, $"SELECT PredictProbability([Gravedad], 'GRAVE O MORTAL') AS P FROM [{m}] NATURAL PREDICTION JOIN (SELECT {valores}) AS t");
                    linea += Pct(r[0]["P"]).PadLeft(21);
                }
                Salida.Linea(linea);
            }
        }

        // ------------------------------------------------------------------ 4. clustering
        private static void Clustering(AdomdConnection cn)
        {
            Salida.Linea(); Salida.Linea("--- Clustering de siniestros: % de graves por cluster y características");
            var cl = Leer(cn, @"SELECT FLATTENED NODE_CAPTION, NODE_SUPPORT, NODE_DESCRIPTION,
                                  (SELECT ATTRIBUTE_VALUE, [PROBABILITY] FROM NODE_DISTRIBUTION WHERE ATTRIBUTE_NAME = 'Gravedad') AS D
                                FROM [Clustering - Siniestros].CONTENT WHERE NODE_TYPE = 5");
            foreach (var c in cl.Where(x => x["ATTRIBUTE_VALUE"]?.ToString() == "GRAVE O MORTAL").OrderByDescending(x => D(x["PROBABILITY"])))
            {
                var desc = string.Join(", ", (c["NODE_DESCRIPTION"]?.ToString() ?? "").Split('\n')
                                       .Select(s => s.Trim().TrimEnd(',').Trim()).Where(s => s.Length > 0 && !s.StartsWith("TotalVictimas")).Take(5));
                Salida.Linea($"  {c["NODE_CAPTION"],-10} {c["NODE_SUPPORT"],6} casos  {Pct(c["PROBABILITY"]),6} graves  | {desc}");
            }
        }

        // ------------------------------------------------------------------ 5. reglas de asociacion
        private static void Asociacion(AdomdConnection cn)
        {
            var reglas = Leer(cn, "SELECT NODE_DESCRIPTION, NODE_PROBABILITY, MSOLAP_NODE_SCORE, NODE_SUPPORT FROM [Reglas de Asociacion].CONTENT WHERE NODE_TYPE = 8");
            var itemsets = Leer(cn, "SELECT NODE_SUPPORT FROM [Reglas de Asociacion].CONTENT WHERE NODE_TYPE = 7");
            Salida.Linea(); Salida.Linea($"--- Reglas de asociación: {itemsets.Count} conjuntos frecuentes y {reglas.Count} reglas. Top reglas -> GRAVE O MORTAL:");
            foreach (var r in reglas.Where(x => x["NODE_DESCRIPTION"].ToString().EndsWith("-> Gravedad = GRAVE O MORTAL"))
                                    .OrderByDescending(x => D(x["MSOLAP_NODE_SCORE"])).Take(8))
                Salida.Linea($"  prob {Pct(r["NODE_PROBABILITY"]),6}  importancia {D(r["MSOLAP_NODE_SCORE"]).ToString("0.00", Es)}  {r["NODE_DESCRIPTION"]}");
        }

        // ------------------------------------------------------------------ 6. series de tiempo
        private static void SerieDeTiempo(AdomdConnection cn)
        {
            Salida.Linea(); Salida.Linea("--- Pronóstico 2026 (Microsoft Time Series, PredictTimeSeries a 12 meses)");
            var s = Leer(cn, "SELECT FLATTENED PredictTimeSeries([Siniestros], 12) AS F FROM [Serie de Tiempo - Siniestros]");
            var m = Leer(cn, "SELECT FLATTENED PredictTimeSeries([Mortales], 12) AS F FROM [Serie de Tiempo - Siniestros]");
            for (int i = 0; i < s.Count; i++)
                Salida.Linea($"  {Convert.ToDateTime(s[i]["$TIME"]):yyyy-MM}   siniestros {D(s[i]["Siniestros"]).ToString("N0", Es),7}   víctimas fatales {D(m[i]["Mortales"]).ToString("N1", Es),5}");
            Salida.Linea($"  TOTAL 2026: {s.Sum(x => D(x["Siniestros"])).ToString("N0", Es)} siniestros y {m.Sum(x => D(x["Mortales"])).ToString("N0", Es)} víctimas fatales");
        }

        // ------------------------------------------------------------------ 7. victima fatal
        private static void VictimaFatal(AdomdConnection cn)
        {
            Salida.Linea(); Salida.Linea("--- Perfil de víctima fatal: hojas del árbol con mayor probabilidad de FALLECER");
            var hojas = Leer(cn, @"SELECT FLATTENED NODE_DESCRIPTION, NODE_SUPPORT,
                                     (SELECT ATTRIBUTE_VALUE, [PROBABILITY] FROM NODE_DISTRIBUTION) AS D
                                   FROM [Arbol de Decision - Victima Fatal].CONTENT WHERE NODE_TYPE = 4");
            foreach (var h in hojas.Where(x => x["ATTRIBUTE_VALUE"]?.ToString() == "FALLECIO").OrderByDescending(x => D(x["PROBABILITY"])).Take(6))
                Salida.Linea($"  {Pct(h["PROBABILITY"]),7}  ({h["NODE_SUPPORT"],5} víctimas)  {h["NODE_DESCRIPTION"]}");
        }

        // ------------------------------------------------------------------ 8. clustering de comunas
        private static void ClusteringComunas(AdomdConnection cn)
        {
            Salida.Linea(); Salida.Linea("--- Segmentación de comunas (Microsoft Clustering, 4 clusters)");
            var cl = Leer(cn, "SELECT NODE_CAPTION, NODE_SUPPORT, NODE_DESCRIPTION FROM [Clustering - Comunas].CONTENT WHERE NODE_TYPE = 5");
            foreach (var c in cl)
            {
                var desc = string.Join(", ", (c["NODE_DESCRIPTION"]?.ToString() ?? "").Split('\n').Select(s => s.Trim().TrimEnd(',').Trim()).Where(s => s.Length > 0).Take(3));
                Salida.Linea($"  {c["NODE_CAPTION"],-10} {c["NODE_SUPPORT"],3} comunas | {desc}");
            }
        }
    }
}
