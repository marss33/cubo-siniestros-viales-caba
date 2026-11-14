using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.AnalysisServices;

namespace CuboSiniestrosViales
{
    /// <summary>
    /// Crea y entrena las estructuras y modelos de mineria de datos (SSAS Data Mining) a partir de las
    /// vistas minables del Data Warehouse, que se arman con JOIN entre las tablas de hechos y sus dimensiones:
    ///   vmin_Siniestros    -> 1 siniestro con datos completos (clasificacion, clustering, asociacion)
    ///   vmin_Victimas      -> 1 victima con sexo y edad (perfil de victima fatal)
    ///   vmin_SerieMensual  -> vector tiempo (mes) + vector dato (series de tiempo)
    ///   vmin_PerfilComunas -> 1 comuna con su perfil porcentual (segmentacion)
    /// </summary>
    internal sealed class ConstructorMineria
    {
        private readonly Database _db;
        private readonly DataSourceView _dsv;
        private readonly List<MiningStructure> _estructuras = new List<MiningStructure>();

        // Algoritmos que permiten "drillthrough" (ver los casos de entrenamiento de cada nodo)
        private static readonly HashSet<string> ConDrillthrough = new HashSet<string>
        {
            "Microsoft_Decision_Trees", "Microsoft_Clustering", "Microsoft_Association_Rules", "Microsoft_Time_Series"
        };

        public ConstructorMineria(Database db)
        {
            _db = db;
            _dsv = db.DataSourceViews.Cast<DataSourceView>().First();
        }

        public void Construir()
        {
            Salida.Titulo("2) MINERIA DE DATOS: ESTRUCTURAS Y MODELOS");
            foreach (var vieja in _db.MiningStructures.Cast<MiningStructure>().ToList()) vieja.Drop();

            // ---- 1) Clasificacion y segmentacion de siniestros (30% de los casos se reservan para prueba)
            var s1 = Estructura("MS Gravedad Siniestros", 30);
            Clave(s1, "vmin_Siniestros", "SiniestroID", MiningStructureColumnTypes.Text);
            foreach (var c in new[] { "FranjaHoraria", "TipoDia", "DiaSemana", "Estacion", "Contexto", "Comuna", "Zona",
                                      "TipoVia", "VehiculoVictima", "Contraparte", "Gravedad" })
                Col(s1, "vmin_Siniestros", c, MiningStructureColumnTypes.Text, MiningStructureColumnContents.Discrete);
            Col(s1, "vmin_Siniestros", "Hora", MiningStructureColumnTypes.Long, MiningStructureColumnContents.Discrete);
            Col(s1, "vmin_Siniestros", "TotalVictimas", MiningStructureColumnTypes.Long, MiningStructureColumnContents.Discrete);
            Modelo(s1, "Arbol de Decision - Gravedad", MiningModelAlgorithms.MicrosoftDecisionTrees, new[] { "Gravedad" });
            Modelo(s1, "Naive Bayes - Gravedad", MiningModelAlgorithms.MicrosoftNaiveBayes, new[] { "Gravedad" });
            Modelo(s1, "Regresion Logistica - Gravedad", MiningModelAlgorithms.MicrosoftLogisticRegression, new[] { "Gravedad" });
            Modelo(s1, "Red Neuronal - Gravedad", MiningModelAlgorithms.MicrosoftNeuralNetwork, new[] { "Gravedad" });
            Modelo(s1, "Clustering - Siniestros", MiningModelAlgorithms.MicrosoftClustering, new[] { "Gravedad" },
                   parametros: new Dictionary<string, object> { { "CLUSTER_COUNT", 6 } });

            // ---- 2) Reglas de asociacion: cada siniestro es una transaccion y cada atributo=valor un item
            var s2 = Estructura("MS Asociacion Siniestros", 0);
            Clave(s2, "vmin_Siniestros", "SiniestroID", MiningStructureColumnTypes.Text);
            var items = new[] { "FranjaHoraria", "TipoDia", "TipoVia", "VehiculoVictima", "Contraparte", "Zona", "Gravedad" };
            foreach (var c in items) Col(s2, "vmin_Siniestros", c, MiningStructureColumnTypes.Text, MiningStructureColumnContents.Discrete);
            Modelo(s2, "Reglas de Asociacion", MiningModelAlgorithms.MicrosoftAssociationRules, items,
                   parametros: new Dictionary<string, object> { { "MINIMUM_SUPPORT", 0.002 }, { "MINIMUM_PROBABILITY", 0.1 }, { "MAXIMUM_ITEMSET_SIZE", 4 } });

            // ---- 3) Serie de tiempo mensual (vector tiempo + vector dato)
            var s3 = Estructura("MS Serie Mensual", 0);
            Clave(s3, "vmin_SerieMensual", "Mes", MiningStructureColumnTypes.Date, MiningStructureColumnContents.KeyTime);
            Col(s3, "vmin_SerieMensual", "Siniestros", MiningStructureColumnTypes.Double, MiningStructureColumnContents.Continuous);
            Col(s3, "vmin_SerieMensual", "Mortales", MiningStructureColumnTypes.Double, MiningStructureColumnContents.Continuous);
            Modelo(s3, "Serie de Tiempo - Siniestros", MiningModelAlgorithms.MicrosoftTimeSeries, new[] { "Siniestros", "Mortales" },
                   parametros: new Dictionary<string, object> { { "PERIODICITY_HINT", "{12}" } });

            // ---- 4) Perfil de victima fatal (30% de prueba)
            var s4 = Estructura("MS Victima Fatal", 30);
            Clave(s4, "vmin_Victimas", "VictimaID", MiningStructureColumnTypes.Long);
            Col(s4, "vmin_Victimas", "Edad", MiningStructureColumnTypes.Long, MiningStructureColumnContents.Continuous);
            Col(s4, "vmin_Victimas", "Hora", MiningStructureColumnTypes.Long, MiningStructureColumnContents.Discrete);
            foreach (var c in new[] { "RangoEtario", "Sexo", "Vehiculo", "TipoVia", "FranjaHoraria", "TipoDia", "Zona", "Desenlace" })
                Col(s4, "vmin_Victimas", c, MiningStructureColumnTypes.Text, MiningStructureColumnContents.Discrete);
            Modelo(s4, "Arbol de Decision - Victima Fatal", MiningModelAlgorithms.MicrosoftDecisionTrees, new[] { "Desenlace" });
            // Naive Bayes no admite columnas continuas: se usa el rango etario en lugar de la edad
            Modelo(s4, "Naive Bayes - Victima Fatal", MiningModelAlgorithms.MicrosoftNaiveBayes, new[] { "Desenlace" }, quitar: new[] { "Edad" });

            // ---- 5) Segmentacion de comunas (1 fila = 1 comuna)
            var s5 = Estructura("MS Perfil Comunas", 0);
            Clave(s5, "vmin_PerfilComunas", "Comuna", MiningStructureColumnTypes.Text);
            Col(s5, "vmin_PerfilComunas", "Zona", MiningStructureColumnTypes.Text, MiningStructureColumnContents.Discrete);
            foreach (var c in new[] { "SiniestrosAnuales", "PctMoto", "PctPeaton", "PctBicicleta", "PctNocturno", "PctFinDeSemana",
                                      "PctViaRapida", "PctTransportePesado", "PctGraveMortal" })
                Col(s5, "vmin_PerfilComunas", c, MiningStructureColumnTypes.Double, MiningStructureColumnContents.Continuous);
            Modelo(s5, "Clustering - Comunas", MiningModelAlgorithms.MicrosoftClustering, new string[0],
                   parametros: new Dictionary<string, object> { { "CLUSTER_COUNT", 4 }, { "MINIMUM_SUPPORT", 1 } });

            var rol = _db.Roles.FindByName("Lectores");
            if (rol != null)
            {
                // si la base se desplego desde otro lado y perdio los miembros, se vuelve a agregar el usuario actual
                string usuario = System.Security.Principal.WindowsIdentity.GetCurrent().Name;
                if (!rol.Members.Cast<RoleMember>().Any(m => string.Equals(m.Name, usuario, StringComparison.OrdinalIgnoreCase)))
                {
                    rol.Members.Add(new RoleMember(usuario));
                    rol.Update();
                }
            }
            foreach (var ms in _estructuras)
            {
                ms.Update(UpdateOptions.ExpandFull);
                if (rol != null) Permisos(ms, rol);
                Salida.Linea($"Estructura '{ms.Name}':");
                Salida.ConProgreso("Entrenando " + string.Join(", ", ms.MiningModels.Cast<MiningModel>().Select(m => m.Algorithm.Replace("Microsoft_", ""))),
                                   () => ms.Process(ProcessType.ProcessFull));
                foreach (MiningModel mm in ms.MiningModels)
                    Salida.Linea($"   {mm.Name,-36} {mm.Algorithm,-32} entrenado");
            }
            Salida.Linea($"Mineria lista: {_estructuras.Count} estructuras, {_estructuras.Sum(e => e.MiningModels.Count)} modelos.");
        }

        // ------------------------------------------------------------------ helpers
        private MiningStructure Estructura(string nombre, int porcentajePrueba)
        {
            var ms = new MiningStructure(nombre, nombre) { Source = new DataSourceViewBinding(_dsv.ID) };
            if (porcentajePrueba > 0)
            {
                ms.HoldoutMaxPercent = porcentajePrueba;   // particion entrenamiento / prueba
                ms.HoldoutSeed = 42;
            }
            _db.MiningStructures.Add(ms);
            _estructuras.Add(ms);
            return ms;
        }

        private void Clave(MiningStructure ms, string vista, string columna, string tipo, string contenido = MiningStructureColumnContents.Key)
        {
            var c = Col(ms, vista, columna, tipo, contenido);
            c.IsKey = true;
        }

        private ScalarMiningStructureColumn Col(MiningStructure ms, string vista, string columna, string tipo, string contenido)
        {
            var c = new ScalarMiningStructureColumn(columna, columna) { Type = tipo, Content = contenido };
            c.KeyColumns.Add(ConstructorCubo.Columna(_dsv, vista, columna));
            ms.Columns.Add(c);
            return c;
        }

        private static MiningModel Modelo(MiningStructure ms, string nombre, string algoritmo, IEnumerable<string> predecir,
                                          IEnumerable<string> quitar = null, Dictionary<string, object> parametros = null)
        {
            var mm = ms.CreateMiningModel(true, nombre);   // todas las columnas como entrada
            mm.Algorithm = algoritmo;
            foreach (var q in quitar ?? Enumerable.Empty<string>())
            {
                var col = mm.Columns.Find(q);
                if (col != null) mm.Columns.Remove(col);
            }
            foreach (var p in predecir) mm.Columns.Find(p).Usage = MiningModelColumnUsages.Predict;
            if (parametros != null)
                foreach (var kv in parametros) mm.AlgorithmParameters.Add(kv.Key, kv.Value);
            if (ConDrillthrough.Contains(algoritmo)) mm.AllowDrillThrough = true;
            return mm;
        }

        private static void Permisos(MiningStructure ms, Role rol)
        {
            var msp = ms.MiningStructurePermissions.Add(rol.ID);
            msp.Read = ReadAccess.Allowed;
            msp.AllowDrillThrough = true;
            msp.Update();
            foreach (MiningModel mm in ms.MiningModels)
            {
                var p = mm.MiningModelPermissions.Add(rol.ID);
                p.Read = ReadAccess.Allowed;
                p.AllowBrowsing = true;
                if (ConDrillthrough.Contains(mm.Algorithm)) p.AllowDrillThrough = true;
                p.Update();
            }
        }
    }
}
