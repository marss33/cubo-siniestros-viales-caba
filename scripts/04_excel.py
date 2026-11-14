"""
04_excel.py - Libro Excel del TP: numero indice base 100 + acumulado (con formulas),
tablas OLAP, datos para tablas dinamicas y resultados de mineria.
Uso: python 04_excel.py <carpeta_del_proyecto>
"""
import sys, os, json
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage

ROOT = sys.argv[1]
M = os.path.join(ROOT, "mineria"); G = os.path.join(ROOT, "graficos"); D = os.path.join(ROOT, "datos_limpios")
OUT = os.path.join(ROOT, "excel"); os.makedirs(OUT, exist_ok=True)
R = json.load(open(os.path.join(M, "resultados.json"), encoding="utf-8"))

AZUL = "1C5CAB"; AZUL_CLARO = "CDE2FB"; GRIS = "F0EFEC"
H = Font(bold=True, color="FFFFFF"); HF = PatternFill("solid", fgColor=AZUL)
TIT = Font(bold=True, size=14, color="0B0B0B"); SUB = Font(italic=True, size=9, color="52514E")
thin = Side(style="thin", color="E1E0D9"); BORDE = Border(top=thin, bottom=thin, left=thin, right=thin)

wb = Workbook()

def hoja(nombre, titulo, subtitulo=None):
    ws = wb.create_sheet(nombre)
    ws["A1"] = titulo; ws["A1"].font = TIT
    if subtitulo:
        ws["A2"] = subtitulo; ws["A2"].font = SUB
    ws.sheet_view.showGridLines = False
    return ws

def volcar(ws, df, fila=4, col=1, formatos=None, tabla=None):
    formatos = formatos or {}
    for j, c in enumerate(df.columns):
        cell = ws.cell(row=fila, column=col + j, value=str(c)); cell.font = H; cell.fill = HF
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True); cell.border = BORDE
    for i, row in enumerate(df.itertuples(index=False), start=1):
        for j, v in enumerate(row):
            if isinstance(v, float) and pd.isna(v): v = None
            cell = ws.cell(row=fila + i, column=col + j, value=v.item() if hasattr(v, "item") else v)
            cell.border = BORDE
            f = formatos.get(df.columns[j])
            if f: cell.number_format = f
    for j, c in enumerate(df.columns):
        largo = max([len(str(c))] + [len(str(x)) for x in df.iloc[:200, j].tolist()])
        ws.column_dimensions[get_column_letter(col + j)].width = min(max(10, largo + 2), 60)
    if tabla:
        ref = f"{get_column_letter(col)}{fila}:{get_column_letter(col + len(df.columns) - 1)}{fila + len(df)}"
        t = Table(displayName=tabla, ref=ref)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
        ws.add_table(t)
    return fila + len(df)

# ------------------------------------------------------------------ Portada
ws = wb.active; ws.title = "Portada"; ws.sheet_view.showGridLines = False
ws["A1"] = "Siniestros Viales - Ciudad Autónoma de Buenos Aires (2019-2025)"; ws["A1"].font = Font(bold=True, size=16)
ws["A2"] = "Base de Datos Aplicada - Data Warehouse, Cubo OLAP y Minería de Datos"; ws["A2"].font = SUB
ws["A3"] = "Fuente: Portal de Datos Abiertos GCBA - Secretaría de Transporte, Observatorio de Movilidad y Seguridad Vial"; ws["A3"].font = SUB
k = R["kpi"]
kpis = [("Siniestros registrados", k["siniestros"], "#,##0"), ("Víctimas totales", k["victimas"], "#,##0"),
        ("Víctimas leves", k["victimas_leves"], "#,##0"), ("Víctimas graves", k["victimas_graves"], "#,##0"),
        ("Víctimas fatales", k["victimas_mortales"], "#,##0"), ("% siniestros graves o mortales", k["pct_grave_mortal"] / 100, "0.00%"),
        ("Promedio de siniestros por día", k["promedio_diario"], "0.0"), ("Período", f"{k['desde']} a {k['hasta']}", None)]
ws["A5"] = "Indicador"; ws["B5"] = "Valor"
for c in ("A5", "B5"): ws[c].font = H; ws[c].fill = HF
for i, (n, v, f) in enumerate(kpis, start=6):
    ws.cell(row=i, column=1, value=n).border = BORDE
    c = ws.cell(row=i, column=2, value=v); c.border = BORDE
    if f: c.number_format = f
ws["A16"] = "Hojas del libro"; ws["A16"].font = Font(bold=True)
hojas_desc = [
    ("Serie_Indice_Base100", "Serie mensual con valor acumulable, número índice base 100 (enero 2019) e índice acumulado. Usa fórmulas."),
    ("Indice_Anual", "Totales anuales con índice base 2019 = 100 y variación interanual (fórmulas)."),
    ("Pivot_Cubo_OLAP", "Tabla dinámica conectada en vivo al cubo SSAS SiniestrosVialesOLAP."),
    ("Pivots_Datos", "Tablas dinámicas sobre la hoja Datos_Cubo (no requieren servidor)."),
    ("OLAP_*", "Cortes del cubo: comuna, vehículo, franja horaria, día, vía, víctimas por sexo y edad."),
    ("MD_*", "Resultados de minería: regresión, pronóstico, clasificación, clustering, asociación, anomalías, correlación."),
    ("Datos_Cubo", "Vista desnormalizada del DW (1 fila = 1 siniestro) para tablas dinámicas / Google Sheets."),
]
for i, (n, d) in enumerate(hojas_desc, start=17):
    ws.cell(row=i, column=1, value=n).font = Font(bold=True, color=AZUL); ws.cell(row=i, column=2, value=d)
ws.column_dimensions["A"].width = 34; ws.column_dimensions["B"].width = 110

# ------------------------------------------------------------------ Serie mensual + indice base 100 (FORMULAS)
men = pd.read_csv(os.path.join(M, "serie_mensual.csv"))
ws = hoja("Serie_Indice_Base100", "Serie mensual de siniestros: valor acumulable y número índice (base enero 2019 = 100)",
          "Índice = Valor del mes / Valor de enero 2019 × 100.  Índice acumulado = Acumulado / Valor de enero 2019 × 100.  Las columnas C a K son fórmulas.")
cab = ["Mes (AAAA-MM)", "Siniestros", "Acumulado", "Índice base 100", "Índice acumulado base 100", "Var. % mensual", "Var. % interanual",
       "Víctimas fatales", "Fatales acumuladas", "Índice fatales base 100", "Siniestros graves o mortales"]
F0 = 4
for j, c in enumerate(cab, start=1):
    cell = ws.cell(row=F0, column=j, value=c); cell.font = H; cell.fill = HF; cell.border = BORDE
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
ws.row_dimensions[F0].height = 32
primera = F0 + 1
for i, r in men.iterrows():
    f = primera + i
    ws.cell(row=f, column=1, value=r["AnioMes"])
    ws.cell(row=f, column=2, value=int(r["Siniestros"]))
    ws.cell(row=f, column=3, value=f"=B{f}" if i == 0 else f"=C{f-1}+B{f}")
    ws.cell(row=f, column=4, value=f"=B{f}/$B${primera}*100")
    ws.cell(row=f, column=5, value=f"=C{f}/$B${primera}*100")
    ws.cell(row=f, column=6, value=None if i == 0 else f"=B{f}/B{f-1}-1")
    ws.cell(row=f, column=7, value=None if i < 12 else f"=B{f}/B{f-12}-1")
    ws.cell(row=f, column=8, value=int(r["Mortales"]))
    ws.cell(row=f, column=9, value=f"=H{f}" if i == 0 else f"=I{f-1}+H{f}")
    ws.cell(row=f, column=10, value=f"=H{f}/$H${primera}*100")
    ws.cell(row=f, column=11, value=int(r["GraveMortal"]))
    for j, fmt in zip(range(1, 12), [None, "#,##0", "#,##0", "0.00", "0.00", "0.0%", "0.0%", "#,##0", "#,##0", "0.00", "#,##0"]):
        c = ws.cell(row=f, column=j); c.border = BORDE
        if fmt: c.number_format = fmt
ultima = primera + len(men) - 1
ft = ultima + 1
ws.cell(row=ft, column=1, value="TOTAL / ÚLTIMO VALOR").font = Font(bold=True)
ws.cell(row=ft, column=2, value=f"=SUM(B{primera}:B{ultima})").number_format = "#,##0"
ws.cell(row=ft, column=3, value=f"=C{ultima}").number_format = "#,##0"
ws.cell(row=ft, column=4, value=f"=D{ultima}").number_format = "0.00"
ws.cell(row=ft, column=5, value=f"=E{ultima}").number_format = "0.00"
ws.cell(row=ft, column=8, value=f"=SUM(H{primera}:H{ultima})").number_format = "#,##0"
ws.cell(row=ft, column=9, value=f"=I{ultima}").number_format = "#,##0"
ws.cell(row=ft, column=11, value=f"=SUM(K{primera}:K{ultima})").number_format = "#,##0"
for j in range(1, 12):
    c = ws.cell(row=ft, column=j); c.fill = PatternFill("solid", fgColor=AZUL_CLARO); c.font = Font(bold=True); c.border = BORDE
ws.cell(row=ft + 1, column=1, value="Control: el último acumulado (C) debe ser igual a la suma total (B).").font = SUB
for j, w in enumerate([14, 11, 12, 12, 14, 11, 11, 11, 12, 12, 13], start=1):
    ws.column_dimensions[get_column_letter(j)].width = w
ws.freeze_panes = f"B{primera}"
ch = LineChart(); ch.title = "Número índice mensual (base enero 2019 = 100)"; ch.height = 9; ch.width = 24
ch.add_data(Reference(ws, min_col=4, min_row=F0, max_row=ultima), titles_from_data=True)
ch.set_categories(Reference(ws, min_col=1, min_row=primera, max_row=ultima)); ch.y_axis.title = "Índice"; ch.legend = None
ch.series[0].graphicalProperties.line.solidFill = "2A78D6"; ch.series[0].graphicalProperties.line.width = 22000
ws.add_chart(ch, "M4")
ch2 = LineChart(); ch2.title = "Siniestros acumulados (valor acumulable)"; ch2.height = 9; ch2.width = 24
ch2.add_data(Reference(ws, min_col=3, min_row=F0, max_row=ultima), titles_from_data=True)
ch2.set_categories(Reference(ws, min_col=1, min_row=primera, max_row=ultima)); ch2.legend = None
ch2.series[0].graphicalProperties.line.solidFill = "1C5CAB"; ch2.series[0].graphicalProperties.line.width = 22000
ws.add_chart(ch2, "M24")

# ------------------------------------------------------------------ Indice anual (FORMULAS)
an = pd.DataFrame(R["anual"])
ws = hoja("Indice_Anual", "Siniestros por año - índice base 2019 = 100", "Columnas D, E, G e I con fórmulas.")
cab = ["Año", "Siniestros", "Víctimas fatales", "Índice base 2019", "Var. % interanual", "Graves o mortales", "% graves o mortales", "Acumulado", "Índice acumulado base 2019"]
for j, c in enumerate(cab, start=1):
    cell = ws.cell(row=4, column=j, value=c); cell.font = H; cell.fill = HF; cell.border = BORDE; cell.alignment = Alignment(wrap_text=True, horizontal="center")
for i, r in an.iterrows():
    f = 5 + i
    vals = [int(r["Anio"]), int(r["Total"]), int(r["VictimasMortales"]), f"=B{f}/$B$5*100", None if i == 0 else f"=B{f}/B{f-1}-1",
            int(r["GRAVE"] + r["MORTAL"]), f"=F{f}/B{f}", f"=B{f}" if i == 0 else f"=H{f-1}+B{f}", f"=H{f}/$B$5*100"]
    for j, (v, fmt) in enumerate(zip(vals, [None, "#,##0", "#,##0", "0.00", "0.0%", "#,##0", "0.00%", "#,##0", "0.00"]), start=1):
        c = ws.cell(row=f, column=j, value=v); c.border = BORDE
        if fmt: c.number_format = fmt
for j in range(1, 10): ws.column_dimensions[get_column_letter(j)].width = 15
ch = BarChart(); ch.title = "Índice anual de siniestros (2019 = 100)"; ch.height = 8; ch.width = 18; ch.legend = None
ch.add_data(Reference(ws, min_col=4, min_row=4, max_row=4 + len(an)), titles_from_data=True)
ch.set_categories(Reference(ws, min_col=1, min_row=5, max_row=4 + len(an)))
ch.series[0].graphicalProperties.solidFill = "2A78D6"
ws.add_chart(ch, "A14")

# ------------------------------------------------------------------ Hojas placeholder para pivots (se completan por COM)
hoja("Pivot_Cubo_OLAP", "Tabla dinámica conectada al cubo OLAP (SSAS)",
     "Conexión: Proveedor MSOLAP - Servidor localhost\\SSAS2019 - Base SiniestrosVialesOLAP - Cubo [Siniestros Viales]. Datos > Actualizar todo para refrescar.")
hoja("Pivots_Datos", "Tablas dinámicas sobre la vista desnormalizada (Datos_Cubo)")

# ------------------------------------------------------------------ OLAP
def olap(nombre, clave, titulo, primera_col):
    df = pd.DataFrame(R[clave]).rename(columns={primera_col: primera_col})
    df = df[[primera_col, "Siniestros", "PctSiniestros", "Victimas", "Graves", "Mortales", "PctGraveMortal"]]
    df.columns = [primera_col, "Siniestros", "% del total", "Víctimas", "Víctimas graves", "Víctimas fatales", "% graves o mortales"]
    df["% del total"] /= 100; df["% graves o mortales"] /= 100
    ws = hoja(nombre, titulo)
    fin = volcar(ws, df, formatos={"Siniestros": "#,##0", "Víctimas": "#,##0", "% del total": "0.00%", "% graves o mortales": "0.00%",
                                   "Víctimas graves": "#,##0", "Víctimas fatales": "#,##0"})
    ch = BarChart(); ch.type = "bar"; ch.title = titulo; ch.height = 9; ch.width = 16; ch.legend = None
    ch.add_data(Reference(ws, min_col=2, min_row=4, max_row=fin), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=5, max_row=fin)); ch.series[0].graphicalProperties.solidFill = "2A78D6"
    ws.add_chart(ch, "J4")
olap("OLAP_Comuna", "olap_comuna", "Siniestros por comuna", "Comuna")
olap("OLAP_Zona", "olap_zona", "Siniestros por zona", "Zona")
olap("OLAP_Vehiculo", "olap_vehiculo_victima", "Siniestros según vehículo de la víctima", "VehiculoVictima")
olap("OLAP_Contraparte", "olap_contraparte", "Siniestros según contraparte", "Contraparte")
olap("OLAP_TipoVia", "olap_tipo_via", "Siniestros por tipo de vía", "TipoVia")
olap("OLAP_Franja", "olap_franja", "Siniestros por franja horaria", "FranjaHoraria")
olap("OLAP_DiaSemana", "olap_dia_semana", "Siniestros por día de la semana", "DiaSemanaNombre")
olap("OLAP_Contexto", "olap_contexto", "Siniestros según contexto (pandemia)", "Contexto")
se = pd.read_csv(os.path.join(M, "victimas_sexo_edad.csv")); fa = pd.read_csv(os.path.join(M, "fallecidos_sexo_edad.csv"))
ws = hoja("OLAP_Victimas", "Víctimas y fallecidos por sexo y rango etario (grupo de medida Víctimas)")
f = volcar(ws, se.rename(columns={"RangoEtario": "Rango etario (víctimas)"}), formatos={c: "#,##0" for c in se.columns})
volcar(ws, fa.rename(columns={"RangoEtario": "Rango etario (fallecidos)"}), fila=f + 3, formatos={c: "#,##0" for c in fa.columns})
ws.add_image(XLImage(os.path.join(G, "16_letalidad_edad.png")), "G4")

# ------------------------------------------------------------------ MINERIA
def img(ws, archivo, celda, escala=0.55):
    im = XLImage(os.path.join(G, archivo)); im.width *= escala; im.height *= escala; ws.add_image(im, celda)

ws = hoja("MD_1_Regresion", "Técnica 1 - Regresión y series de tiempo",
          "Vista minable: vector tiempo (mes) + vector dato (siniestros). Regresión lineal sin meses ASPO; descomposición aditiva; Holt-Winters.")
rg = R["regresion"]; pr = R["pronostico"]
filas = [("Pendiente (siniestros/mes por mes)", rg["pendiente_mensual"]), ("Aumento anual estimado del nivel mensual", rg["aumento_anual_estimado"]),
         ("R²", rg["r2"]), ("p-valor de la pendiente", rg["p_valor"]),
         ("MAPE Holt-Winters (validación 2025)", pr["mape_test_2025"] / 100), ("MAPE modelo ingenuo (mismo mes año anterior)", pr["mape_naive"] / 100),
         ("Total real 2025", pr["real_2025"]), ("Total pronosticado 2025 (validación)", pr["pred_2025"]), ("Pronóstico total 2026", pr["total_2026"])]
f = volcar(ws, pd.DataFrame(filas, columns=["Indicador", "Valor"]), formatos={"Valor": "#,##0.0000"})
for rr_, fmt in [(9, "0.00%"), (10, "0.00%"), (11, "#,##0"), (12, "#,##0"), (13, "#,##0")]:
    ws.cell(row=rr_, column=2).number_format = fmt
pf = pd.read_csv(os.path.join(M, "pronostico_2026.csv"))
f = volcar(ws, pf, fila=f + 3, formatos={"Pronostico": "#,##0", "LimInf95": "#,##0", "LimSup95": "#,##0"})
est = pd.DataFrame({"Mes": list(range(1, 13)), "Efecto estacional (siniestros)": [R["estacionalidad"][str(m)] for m in range(1, 13)]})
volcar(ws, est, fila=f + 3, formatos={"Efecto estacional (siniestros)": "0.0"})
img(ws, "11_pronostico_holt_winters.png", "E4"); img(ws, "10_descomposicion_serie.png", "E25", 0.5)

ws = hoja("MD_2_Clasificacion", "Técnica 2 - Clasificación supervisada: ¿el siniestro será grave o mortal?",
          f"Vista minable: {R['sesgo_sin_dato']['n_completos']:,} siniestros con datos completos; 70% entrenamiento / 30% prueba estratificado; validación cruzada 5 pliegues.".replace(",", "."))
met = pd.DataFrame(R["clasificacion"])
f = volcar(ws, met, formatos={c: "0.0000" for c in met.columns if c != "Modelo"})
imp = pd.DataFrame(list(R["importancia_variables"].items()), columns=["Variable", "Importancia RF (%)"])
f = volcar(ws, imp, fila=f + 3, formatos={"Importancia RF (%)": "0.00"})
odds = pd.DataFrame(list(R["odds_ratio_top"].items()) + list(R["odds_ratio_bottom"].items()), columns=["Categoría", "Odds ratio (reg. logística)"])
f = volcar(ws, odds, fila=f + 3, formatos={"Odds ratio (reg. logística)": "0.00"})
cm = R["matriz_confusion_arbol"]
f = volcar(ws, pd.DataFrame([["Real leve", cm[0][0], cm[0][1]], ["Real grave/mortal", cm[1][0], cm[1][1]]],
                            columns=["Matriz de confusión (árbol)", "Predice leve", "Predice grave/mortal"]), fila=f + 3)
vf = R["victima_fatal"]
vfdf = pd.DataFrame([("Víctimas analizadas", vf["n"]), ("Fallecidos", vf["fallecidos"]), ("AUC", vf["auc"]), ("Recall", vf["recall"]),
                     ("Edad media fallecidos", vf["edad_media_fallecidos"]), ("Edad media resto", vf["edad_media_resto"])],
                    columns=["Árbol 2: perfil de víctima fatal", "Valor"])
volcar(ws, vfdf, fila=f + 3, formatos={"Valor": "#,##0.00"})
img(ws, "12_roc_clasificacion.png", "K4", 0.6); img(ws, "14_importancia_variables.png", "K30", 0.6)
ws2 = hoja("MD_2b_Arbol", "Árbol de decisión (vista simplificada) y reglas")
img(ws2, "15_arbol_decision.png", "A3", 0.5)
for i, linea in enumerate(open(os.path.join(M, "arbol_reglas.txt"), encoding="utf-8").read().splitlines()[:120], start=30):
    ws2.cell(row=i, column=1, value=linea).font = Font(name="Consolas", size=9)

ws = hoja("MD_3_Clustering", "Técnica 3 - Agrupamiento (K-Means + jerárquico) de comunas y DBSCAN de puntos negros",
          "Vista minable: 1 fila por comuna con su perfil porcentual estandarizado (z-score).")
cl = pd.read_csv(os.path.join(M, "clusters_comunas.csv"))
f = volcar(ws, cl, formatos={c: "0.00" for c in cl.columns if c not in ("Comuna", "Cluster", "Perfil")})
cod = pd.DataFrame({"k": list(R["kmeans"]["inercias"].keys()), "Inercia": list(R["kmeans"]["inercias"].values()), "Silueta": list(R["kmeans"]["siluetas"].values())})
f = volcar(ws, cod, fila=f + 3, formatos={"Inercia": "0.00", "Silueta": "0.000"})
hs = pd.read_csv(os.path.join(M, "dbscan_puntos_negros.csv")).head(20)
volcar(ws, hs, fila=f + 3, formatos={"Lat": "0.00000", "Lon": "0.00000"})
img(ws, "18_clusters_comunas.png", "N4", 0.5); img(ws, "20_dbscan_puntos_negros.png", "N28", 0.5)

ws = hoja("MD_4_Asociacion", "Técnica 4 - Reglas de asociación (Apriori)",
          "Vista minable: 1 transacción por siniestro, 1 columna (ítem) por característica - tabla one-hot. Lift > 1 = asociación positiva.")
rg = pd.read_csv(os.path.join(M, "reglas_grave_mortal.csv")); rgen = pd.read_csv(os.path.join(M, "reglas_generales.csv"))
ws.cell(row=3, column=1, value="Reglas con consecuente GRAVE O MORTAL").font = Font(bold=True)
f = volcar(ws, rg, formatos={"support": "0.00%", "confidence": "0.00%", "lift": "0.00", "leverage": "0.0000", "conviction": "0.00"})
ws.cell(row=f + 2, column=1, value="Reglas generales (patrones de co-ocurrencia)").font = Font(bold=True)
volcar(ws, rgen, fila=f + 3, formatos={"support": "0.00%", "confidence": "0.00%", "lift": "0.00", "leverage": "0.0000", "conviction": "0.00"})
ws.column_dimensions["A"].width = 60; ws.column_dimensions["B"].width = 34

ws = hoja("MD_5_Anomalias", "Técnica 5 - Detección de anomalías (campana de Gauss / z-score + Isolation Forest)",
          "Residuo = siniestros observados - esperados (media móvil 28 días × factor del día de semana). Anomalía si |z| > 3.")
an_ = pd.read_csv(os.path.join(M, "anomalias_diarias.csv"))
volcar(ws, an_[["Fecha", "DiaSemanaNombre", "Siniestros", "Esperado", "Z", "Mortales", "AnomaliaGauss", "AnomaliaIsolationForest", "ScoreIF"]],
       formatos={"Esperado": "0.0", "Z": "0.00", "ScoreIF": "0.000"})
img(ws, "22_anomalias_gauss.png", "L4", 0.5); img(ws, "23_anomalias_serie.png", "L25", 0.45)

ws = hoja("MD_6_Correlacion", "Técnica 6 - Correlación (Pearson / Spearman)")
co = pd.read_csv(os.path.join(M, "correlacion_pearson_mensual.csv")).rename(columns={"Unnamed: 0": "Variable"})
f = volcar(ws, co, formatos={c: "0.00" for c in co.columns if c != "Variable"})
ch_ = R["correlacion_hora"]; cv_ = R["correlacion_viarapida_gravedad_comuna"]
volcar(ws, pd.DataFrame([("Volumen por hora vs % grave/mortal - Pearson", ch_["pearson"], ch_["p"]),
                         ("Volumen por hora vs % grave/mortal - Spearman", ch_["spearman"], ch_["p_s"]),
                         ("% vía rápida vs % grave/mortal por comuna - Pearson", cv_["pearson"], cv_["p"])],
                        columns=["Par de variables", "Coeficiente", "p-valor"]), fila=f + 3, formatos={"Coeficiente": "0.000", "p-valor": "0.0000000"})
img(ws, "24_correlacion.png", "L4", 0.5); img(ws, "25_correlacion_hora.png", "L30", 0.5)

# ------------------------------------------------------------------ Datos para pivots / Google Sheets
S = pd.read_csv(os.path.join(M, "vista_desnormalizada_siniestros.csv"), low_memory=False)
cols = ["SiniestroID", "Fecha", "Anio", "Trimestre", "MesNumero", "MesNombre", "AnioMes", "DiaSemanaNombre", "TipoDia", "Estacion", "Contexto",
        "HoraKey", "FranjaHoraria", "Comuna", "Zona", "TipoVia", "CategoriaVia", "VehiculoVictima", "CatVehVictima", "Contraparte",
        "Gravedad", "CantSiniestros", "TotalVictimas", "VictimasLeves", "VictimasGraves", "VictimasMortales"]
S = S[cols].rename(columns={"HoraKey": "Hora", "CatVehVictima": "CategoriaVehiculoVictima", "Anio": "Año"})
S.to_csv(os.path.join(OUT, "Datos_Cubo_Siniestros_GoogleSheets.csv"), index=False, encoding="utf-8-sig")
ws = wb.create_sheet("Datos_Cubo")
ws.append(list(S.columns))
for row in S.itertuples(index=False):
    ws.append([v.item() if hasattr(v, "item") else v for v in row])
t = Table(displayName="DatosCubo", ref=f"A1:{get_column_letter(len(S.columns))}{len(S) + 1}")
t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True); ws.add_table(t)
ws.freeze_panes = "A2"
for j in range(1, len(S.columns) + 1): ws.column_dimensions[get_column_letter(j)].width = 16

dest = os.path.join(OUT, "TP_Siniestros_Viales_CABA.xlsx")
wb.save(dest)
print("OK", dest)
