"""
08_evaluacion_ssas.py - Evalua los modelos de mineria de SSAS (Visual Studio) con sus casos de prueba
(holdout 30%) y genera los graficos de la seccion de mineria en SSAS.
Uso: python 08_evaluacion_ssas.py <carpeta_del_proyecto>
"""
import sys, os, json, re, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from estilo import *
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from sklearn.metrics import roc_auc_score, roc_curve, confusion_matrix, precision_score, recall_score, f1_score, accuracy_score

ROOT = sys.argv[1]
M = os.path.join(ROOT, "mineria"); G = os.path.join(ROOT, "graficos")
RS = json.load(open(os.path.join(M, "resultados_ssas.json"), encoding="utf-8-sig"))
E = {}

def evaluar(archivo, clase_col, positivo):
    d = pd.read_csv(os.path.join(M, archivo), sep=";")
    y = (d[clase_col] == positivo).astype(int).values; p = d["P"].astype(float).values
    fpr, tpr, thr = roc_curve(y, p)
    j = np.argmax(tpr - fpr); umbral = float(thr[j])
    yp = (p >= umbral).astype(int)
    cm = confusion_matrix(y, yp)
    orden = np.argsort(-p); top = orden[: int(len(p) * 0.10)]
    return {"n": int(len(y)), "positivos": int(y.sum()), "auc": float(roc_auc_score(y, p)), "umbral": umbral,
            "accuracy": float(accuracy_score(y, yp)), "precision": float(precision_score(y, yp)), "recall": float(recall_score(y, yp)),
            "f1": float(f1_score(y, yp)), "cm": cm.tolist(), "lift_top10": float(y[top].mean() / y.mean()),
            "captura_top20": float(y[orden[: int(len(p) * 0.20)]].sum() / y.sum())}, (fpr, tpr), (y, p)

mods_g = ["Arbol de Decision - Gravedad", "Naive Bayes - Gravedad", "Regresion Logistica - Gravedad", "Red Neuronal - Gravedad"]
mods_v = ["Arbol de Decision - Victima Fatal", "Naive Bayes - Victima Fatal"]
arch = lambda m: "predicciones_ssas_" + re.sub(r"[^A-Za-z]", "_", m) + ".csv"
rocs, datos = {}, {}
for m in mods_g:
    E[m], rocs[m], datos[m] = evaluar(arch(m), "Gravedad", "GRAVE O MORTAL")
for m in mods_v:
    E[m], rocs[m], datos[m] = evaluar(arch(m), "Desenlace", "FALLECIO")

# ---- ROC de los 4 modelos de gravedad (SSAS)
fig, ax = plt.subplots(figsize=(6.6, 5.4))
for m, c in zip(mods_g, [AZUL, NARANJA, AQUA, VIOLETA]):
    ax.plot(*rocs[m], color=c, label=f"{m.replace(' - Gravedad', '')} (AUC {E[m]['auc']:.3f})")
ax.plot([0, 1], [0, 1], color=BASE, ls="--", lw=1)
ax.set_xlabel("Tasa de falsos positivos"); ax.set_ylabel("Tasa de verdaderos positivos")
ax.legend(loc="lower right", fontsize=8.5); ax.set_title("SSAS: curvas ROC sobre casos de prueba")
guardar(fig, os.path.join(G, "30_ssas_roc_gravedad.png"), "Fuente: modelos de mineria SSAS 2019 (DMX), 11.820 casos de prueba")

# ---- Grafico de elevacion (lift) acumulado, como el "Mining Accuracy Chart" de Visual Studio
fig, ax = plt.subplots(figsize=(7.4, 5.2))
for m, c in zip(mods_g, [AZUL, NARANJA, AQUA, VIOLETA]):
    y, p = datos[m]; o = np.argsort(-p); cum = np.cumsum(y[o]) / y.sum()
    x = np.arange(1, len(y) + 1) / len(y)
    ax.plot(x * 100, cum * 100, color=c, label=m.replace(" - Gravedad", ""))
y0, _ = datos[mods_g[0]]; o_ideal = np.sort(y0)[::-1]
ax.plot(np.arange(1, len(y0) + 1) / len(y0) * 100, np.cumsum(o_ideal) / y0.sum() * 100, color=MUTED, lw=1.2, ls=":", label="Modelo ideal")
ax.plot([0, 100], [0, 100], color=BASE, ls="--", lw=1, label="Selección al azar")
ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0)); ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
ax.set_xlabel("% de siniestros revisados (ordenados por probabilidad)"); ax.set_ylabel("% de siniestros graves capturados")
ax.legend(loc="lower right", fontsize=8.5); ax.set_title("SSAS: gráfico de elevación (lift) acumulado")
guardar(fig, os.path.join(G, "31_ssas_lift.png"), "Fuente: modelos de mineria SSAS 2019 (DMX), 11.820 casos de prueba")

# ---- Escenarios (consultas singleton DMX)
esc = pd.DataFrame(RS["escenarios"]).set_index("Escenario")[mods_g]
fig, ax = plt.subplots(figsize=(10, 4.8))
yi = np.arange(len(esc)); h = 0.19
for k, (m, c) in enumerate(zip(mods_g, [AZUL, NARANJA, AQUA, VIOLETA])):
    ax.barh(yi + (k - 1.5) * (h + 0.01), esc[m] * 100, h, color=c, label=m.replace(" - Gravedad", ""))
base = 2722 / 39403 * 100
ax.axvline(base, color=CRITICO, ls="--", lw=1.2); ax.text(base + 0.4, len(esc) - 0.45, f"tasa base {base:.1f}%", color=CRITICO, fontsize=8.5)
ax.set_yticks(yi); ax.set_yticklabels(esc.index); ax.invert_yaxis()
ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0)); ax.grid(axis="y", visible=False)
ax.legend(loc="lower right", fontsize=8); ax.set_title("SSAS: probabilidad de siniestro grave o mortal por escenario (DMX)")
guardar(fig, os.path.join(G, "32_ssas_escenarios.png"), "Fuente: consultas de prediccion singleton DMX sobre los 4 modelos SSAS")

# ---- Serie de tiempo SSAS vs real vs Holt-Winters (Python)
men = pd.read_csv(os.path.join(M, "serie_mensual.csv"))
real = pd.Series(men["Siniestros"].values, index=pd.to_datetime(men["AnioMes"] + "-01"))
def fecha(s): return pd.to_datetime(int(re.search(r"-?\d+", s).group(0)), unit="ms").to_period("M").to_timestamp()
ts = pd.Series([r["Siniestros"] for r in RS["pronostico_siniestros"]], index=[fecha(r["$TIME"]) for r in RS["pronostico_siniestros"]])
tsm = pd.Series([r["Mortales"] for r in RS["pronostico_mortales"]], index=[fecha(r["$TIME"]) for r in RS["pronostico_mortales"]])
hw = pd.read_csv(os.path.join(M, "pronostico_2026.csv")); hw = pd.Series(hw["Pronostico"].values, index=pd.to_datetime(hw["Mes"] + "-01"))
fig, ax = plt.subplots(figsize=(11, 4.4))
ax.plot(real.index, real.values, color=AZUL, label="Real 2019-2025")
ax.plot(ts.index, ts.values, color=NARANJA, label=f"SSAS Microsoft Time Series 2026 ({ts.sum():,.0f})".replace(",", "."))
ax.plot(hw.index, hw.values, color=VERDE, ls="--", label=f"Python Holt-Winters 2026 ({hw.sum():,.0f})".replace(",", "."))
ax.legend(loc="lower right"); ax.grid(axis="x", visible=False)
ax.set_title("Pronóstico de siniestros mensuales 2026: SSAS (ARTXP/ARIMA) vs. Holt-Winters")
guardar(fig, os.path.join(G, "33_ssas_series_tiempo.png"), "Fuente: modelo Microsoft Time Series (SSAS 2019) y Holt-Winters (statsmodels)")
E["ts"] = {"total_2026_ssas": float(ts.sum()), "total_2026_hw": float(hw.sum()), "mortales_2026_ssas": float(tsm.sum()),
           "mensual": {d.strftime("%Y-%m"): float(v) for d, v in ts.items()}}

# ---- Reglas de asociacion SSAS hacia GRAVE O MORTAL
rg = pd.DataFrame(RS["reglas_grave"]).head(10)
rg["regla"] = rg["NODE_DESCRIPTION"].str.replace(" -> Gravedad = GRAVE O MORTAL", "", regex=False)
fig, ax = plt.subplots(figsize=(11, 5))
ax.barh(rg["regla"], rg["NODE_PROBABILITY"] * 100, color=NARANJA, height=0.6)
ax.axvline(base, color=CRITICO, ls="--", lw=1.2); ax.text(base + 0.3, -0.6, f"tasa base {base:.1f}%", color=CRITICO, fontsize=8.5)
for i, (pv, imp) in enumerate(zip(rg["NODE_PROBABILITY"], rg["MSOLAP_NODE_SCORE"])):
    ax.text(pv * 100 + 0.3, i, f"{pv*100:.1f}%  (imp. {imp:.2f})", va="center", fontsize=8, color=INK2)
ax.invert_yaxis(); ax.grid(axis="y", visible=False); ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
ax.tick_params(axis="y", labelsize=8); ax.set_xlim(0, 32)
ax.set_title("SSAS Association Rules: reglas → Gravedad = GRAVE O MORTAL (probabilidad)")
guardar(fig, os.path.join(G, "34_ssas_reglas.png"), "Fuente: modelo Microsoft Association Rules (SSAS 2019)")

# ---- Clusters de siniestros SSAS
cl = pd.DataFrame(RS["clusters_siniestros"]).sort_values("NODE_CAPTION")
fig, ax = plt.subplots(figsize=(8.6, 4.2))
ax.bar(cl["NODE_CAPTION"], cl["PROBABILITY"] * 100, color=AZUL, width=0.6)
for i, (pv, s) in enumerate(zip(cl["PROBABILITY"], cl["NODE_SUPPORT"])):
    ax.text(i, pv * 100 + 0.15, f"{pv*100:.1f}%\n{int(s):,} casos".replace(",", "."), ha="center", fontsize=8.5, color=INK2)
ax.axhline(base, color=CRITICO, ls="--", lw=1.2)
ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0)); ax.grid(axis="x", visible=False); ax.set_ylim(0, 11.5)
ax.set_title("SSAS Clustering: % de siniestros graves o mortales por cluster")
guardar(fig, os.path.join(G, "35_ssas_clusters.png"), "Fuente: modelo Microsoft Clustering (SSAS 2019), 27.583 casos de entrenamiento")

with open(os.path.join(M, "evaluacion_ssas.json"), "w", encoding="utf-8") as f:
    json.dump(E, f, indent=1, ensure_ascii=False)
for m in mods_g + mods_v:
    e = E[m]; print(f"{m:38s} AUC={e['auc']:.3f} umbral={e['umbral']:.3f} recall={e['recall']:.3f} prec={e['precision']:.3f} lift10={e['lift_top10']:.2f} cm={e['cm']}")
print(E["ts"]["total_2026_ssas"], E["ts"]["total_2026_hw"], E["ts"]["mortales_2026_ssas"])
