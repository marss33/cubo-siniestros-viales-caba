using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.AnalysisServices.AdomdClient;

namespace CuboSiniestrosViales
{
    /// <summary>Consultas MDX de validacion del cubo (equivalentes a arrastrar campos en el Cube Browser).</summary>
    internal static class ConsultasMdx
    {
        private static readonly (string titulo, string mdx)[] Consultas =
        {
            ("Totales por año con índice base 2019 = 100 y variación interanual", @"
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Total Victimas], [Measures].[Victimas Mortales],
         [Measures].[% Graves o Mortales], [Measures].[Indice Anual Base 2019], [Measures].[Variacion Interanual %] } ON COLUMNS,
       [Tiempo].[Calendario].[Anio].MEMBERS ON ROWS
FROM [Siniestros Viales]"),
            ("Serie mensual: valor, ACUMULADO e ÍNDICE BASE 100 (enero 2019 = 100) - primeros 13 meses", @"
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Siniestros Acumulados],
         [Measures].[Indice Base 100], [Measures].[Indice Acumulado Base 100] } ON COLUMNS,
       HEAD([Tiempo].[Calendario].[Mes].MEMBERS, 13) ON ROWS
FROM [Siniestros Viales]"),
            ("Últimos 3 meses (la última fila del acumulado = total del período)", @"
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Siniestros Acumulados], [Measures].[Indice Base 100],
         [Measures].[Indice Acumulado Base 100] } ON COLUMNS,
       TAIL([Tiempo].[Calendario].[Mes].MEMBERS, 3) ON ROWS
FROM [Siniestros Viales]"),
            ("Jerarquía Zona > Comuna", @"
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Victimas Mortales], [Measures].[% Graves o Mortales] } ON COLUMNS,
       NON EMPTY [Comuna].[Zona - Comuna].MEMBERS ON ROWS
FROM [Siniestros Viales]"),
            ("Top 5 comunas con mayor % de siniestros graves o mortales", @"
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Victimas Mortales], [Measures].[% Graves o Mortales] } ON COLUMNS,
       TOPCOUNT(FILTER([Comuna].[Comuna].[Comuna].MEMBERS, [Comuna].[Comuna].CurrentMember.Name <> ""SIN DATO""),
                5, [Measures].[% Graves o Mortales]) ON ROWS
FROM [Siniestros Viales]"),
            ("Vehículo de la víctima x Gravedad", @"
SELECT [Gravedad].[Gravedad].[Gravedad].MEMBERS * { [Measures].[Cantidad Siniestros] } ON COLUMNS,
       NON EMPTY [Vehiculo Victima].[Vehiculo].[Vehiculo].MEMBERS ON ROWS
FROM [Siniestros Viales]"),
            ("Letalidad por rango etario y sexo (grupo de medida Victimas)", @"
SELECT [Sexo].[Sexo].[Sexo].MEMBERS * { [Measures].[Letalidad %] } ON COLUMNS,
       [Rango Etario].[Rango Etario].[Rango Etario].MEMBERS ON ROWS
FROM [Siniestros Viales]"),
            ("Impacto de la pandemia: pre-pandemia, ASPO y post-ASPO", @"
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Victimas Mortales], [Measures].[% Graves o Mortales],
         [Measures].[Victimas por Siniestro] } ON COLUMNS,
       [Tiempo].[Contexto].[Contexto].MEMBERS ON ROWS
FROM [Siniestros Viales]"),
            ("Estacionalidad mensual (acumulado 2019-2025)", @"
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Victimas Mortales], [Measures].[% Graves o Mortales] } ON COLUMNS,
       [Tiempo].[Mes del Anio].[Mes del Anio].MEMBERS ON ROWS
FROM [Siniestros Viales]"),
            ("Top 5 contrapartes con más víctimas fatales", @"
SELECT { [Measures].[Victimas Mortales], [Measures].[Cantidad Siniestros], [Measures].[% Graves o Mortales] } ON COLUMNS,
       TOPCOUNT(FILTER([Contraparte].[Vehiculo].[Vehiculo].MEMBERS, [Contraparte].[Vehiculo].CurrentMember.Name <> ""SIN DATO""),
                5, [Measures].[Victimas Mortales]) ON ROWS
FROM [Siniestros Viales]"),
            ("Evolución anual de siniestros por zona", @"
SELECT [Tiempo].[Calendario].[Anio].MEMBERS ON COLUMNS,
       FILTER([Comuna].[Zona].[Zona].MEMBERS, [Comuna].[Zona].CurrentMember.Name <> ""SIN DATO"") ON ROWS
FROM [Siniestros Viales]
WHERE [Measures].[Cantidad Siniestros]"),
            ("Siniestralidad por día de la semana", @"
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Victimas Mortales], [Measures].[% Graves o Mortales] } ON COLUMNS,
       [Tiempo].[Dia de la Semana].[Dia de la Semana].MEMBERS ON ROWS
FROM [Siniestros Viales]"),
            ("Gravedad por categoría y tipo de vía", @"
SELECT { [Measures].[Cantidad Siniestros], [Measures].[Victimas Mortales], [Measures].[% Graves o Mortales],
         [Measures].[Victimas por Siniestro] } ON COLUMNS,
       FILTER(DESCENDANTS([Tipo de Via].[Categoria - Tipo de Via].[All], 1, SELF_AND_AFTER),
              [Tipo de Via].[Categoria - Tipo de Via].CurrentMember.Name <> ""SIN DATO"") ON ROWS
FROM [Siniestros Viales]"),
            ("Hora pico vs. fuera de hora pico, día hábil vs. fin de semana", @"
SELECT [Tiempo].[Tipo de Dia].[Tipo de Dia].MEMBERS * { [Measures].[Cantidad Siniestros], [Measures].[% Graves o Mortales] } ON COLUMNS,
       FILTER([Hora].[Hora Pico].[Hora Pico].MEMBERS, [Hora].[Hora Pico].CurrentMember.Name <> ""SIN DATO"") ON ROWS
FROM [Siniestros Viales]"),
        };

        public static void Ejecutar(string servidor)
        {
            Salida.Titulo("3) CONSULTAS MDX SOBRE EL CUBO");
            using (var cn = new AdomdConnection($"Data Source={servidor};Catalog={Configuracion.BaseOlap}"))
            {
                cn.Open();
                foreach (var (titulo, mdx) in Consultas)
                {
                    Salida.Linea(); Salida.Linea("--- " + titulo);
                    var cs = new AdomdCommand(mdx, cn).ExecuteCellSet();
                    ImprimirCellSet(cs);
                }
            }
        }

        internal static void ImprimirCellSet(CellSet cs)
        {
            var cols = cs.Axes[0].Positions.Cast<Position>()
                         .Select(p => string.Join(" / ", p.Members.Cast<Member>().Select(m => m.Caption))).ToList();
            Salida.Linea(new string(' ', 28) + string.Concat(cols.Select(c => Recortar(c, 22).PadLeft(24))));
            int fila = 0;
            foreach (Position p in cs.Axes[1].Positions)
            {
                string nombre = string.Join(" / ", p.Members.Cast<Member>().Select(m => m.Caption));
                var linea = Recortar(nombre, 27).PadRight(28);
                for (int c = 0; c < cols.Count; c++) linea += (cs.Cells[c, fila].FormattedValue ?? "").PadLeft(24);
                Salida.Linea(linea);
                fila++;
            }
        }

        private static string Recortar(string s, int n) => s.Length <= n ? s : s.Substring(0, n);
    }
}
