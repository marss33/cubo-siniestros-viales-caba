"""
02_mineria.py - Mineria de datos sobre el Data Warehouse de Siniestros Viales CABA.
Sigue las fases vistas en clase: fuente -> recopilacion DW -> ETL/vista minable -> algoritmo
-> evaluacion -> resultados. Cada tecnica arma SU vista minable a partir de la estrella.

Tecnicas:
  1. Regresion / series de tiempo (tendencia lineal, descomposicion estacional, Holt-Winters)
  2. Clasificacion supervisada (Arbol de decision, Random Forest, Regresion logistica)
     2b. Clasificacion de victimas fatales (perfil de victima)
  3. Agrupamiento (K-Means + jerarquico sobre comunas; DBSCAN de puntos negros)
  4. Reglas de asociacion (Apriori)
  5. Deteccion de anomalias (campana de Gauss / z-score + Isolation Forest)
  6. Correlacion (Pearson / Spearman)
Uso: python 02_mineria.py <carpeta_del_proyecto>
"""
import sys, os, json, warnings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from estilo import *
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from scipy import stats
from scipy.cluster.hierarchy import linkage, dendrogram
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.tree import DecisionTreeClassifier, export_text, plot_tree
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
                             roc_curve, confusion_matrix, classification_report)
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, DBSCAN
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from mlxtend.frequent_patterns import apriori, association_rules

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "datos_limpios")
G = os.path.join(ROOT, "graficos"); os.makedirs(G, exist_ok=True)
M = os.path.join(ROOT, "mineria"); os.makedirs(M, exist_ok=True)
R = {}  # resultados para Excel y documento
SEED = 42

def rd(n): return pd.read_csv(os.path.join(D, n + ".csv"), encoding="utf-8")
T, HO, CO, TV, VE, GR = rd("DimTiempo"), rd("DimHora"), rd("DimComuna"), rd("DimTipoVia"), rd("DimVehiculo"), rd("DimGravedad")
SX, RE, RO = rd("DimSexo"), rd("DimRangoEtario"), rd("DimRolVictima")
FS, FV = rd("FactSiniestro"), rd("FactVictima")

# Vista desnormalizada (la "estrella" aplanada) = base de las vistas minables
S = (FS.merge(T, on="FechaKey").merge(HO, on="HoraKey").merge(CO, on="ComunaKey").merge(TV, on="TipoViaKey")
       .merge(VE.rename(columns={"VehiculoKey": "VehiculoVictimaKey", "Vehiculo": "VehiculoVictima", "CategoriaVehiculo": "CatVehVictima"}), on="VehiculoVictimaKey")
       .merge(VE.rename(columns={"VehiculoKey": "ContraparteKey", "Vehiculo": "Contraparte", "CategoriaVehiculo": "CatContraparte"}), on="ContraparteKey")
       .merge(GR, on="GravedadKey"))
S["GraveMortal"] = (S["GravedadKey"] >= 2).astype(int)
S.to_csv(os.path.join(M, "vista_desnormalizada_siniestros.csv"), index=False, encoding="utf-8-sig")
V = (FV.merge(T, on="FechaKey").merge(HO, on="HoraKey").merge(CO, on="ComunaKey").merge(TV, on="TipoViaKey")
       .merge(VE, on="VehiculoKey").merge(SX, on="SexoKey").merge(RE, on="RangoEtarioKey").merge(RO, on="RolKey").merge(GR, on="GravedadKey"))

# ============================================================ 0. DESCRIPTIVO (OLAP)
R["kpi"] = {
    "siniestros": int(len(S)), "victimas": int(S["TotalVictimas"].sum()),
    "victimas_leves": int(S["VictimasLeves"].sum()), "victimas_graves": int(S["VictimasGraves"].sum()),
    "victimas_mortales": int(S["VictimasMortales"].sum()),
    "pct_grave_mortal": float(S["GraveMortal"].mean() * 100),
    "desde": T["Fecha"].min(), "hasta": T["Fecha"].max(),
    "promedio_diario": float(len(S) / T["FechaKey"].nunique()),
}
anual = S.pivot_table(index="Anio", columns="Gravedad", values="CantSiniestros", aggfunc="sum", fill_value=0)
anual["Total"] = anual.sum(axis=1)
anual["VictimasMortales"] = S.groupby("Anio")["VictimasMortales"].sum()
anual["IndiceBase2019"] = anual["Total"] / anual.loc[2019, "Total"] * 100
anual["PctGraveMortal"] = (anual["GRAVE"] + anual["MORTAL"]) / anual["Total"] * 100
anual.to_csv(os.path.join(M, "anual.csv"), encoding="utf-8-sig")
R["anual"] = anual.reset_index().to_dict(orient="records")

def tabla(col, orden=None):
    t = S.groupby(col).agg(Siniestros=("CantSiniestros", "sum"), Victimas=("TotalVictimas", "sum"),
                           Graves=("VictimasGraves", "sum"), Mortales=("VictimasMortales", "sum"),
                           PctGraveMortal=("GraveMortal", "mean"))
    t["PctGraveMortal"] *= 100
    t["PctSiniestros"] = t["Siniestros"] / t["Siniestros"].sum() * 100
    return t.sort_values("Siniestros", ascending=False) if orden is None else t.loc[[o for o in orden if o in t.index]]
tabs = {
    "comuna": tabla("Comuna"), "zona": tabla("Zona"), "vehiculo_victima": tabla("VehiculoVictima"),
    "contraparte": tabla("Contraparte"), "tipo_via": tabla("TipoVia"),
    "franja": tabla("FranjaHoraria", sorted(S["FranjaHoraria"].unique())),
    "dia_semana": tabla("DiaSemanaNombre", ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]),
    "contexto": tabla("Contexto", sorted(S["Contexto"].unique())), "estacion": tabla("Estacion"),
}
for k, t in tabs.items():
    t.to_csv(os.path.join(M, f"olap_{k}.csv"), encoding="utf-8-sig")
    R["olap_" + k] = t.reset_index().round(2).to_dict(orient="records")

# victimas por sexo y edad
vic = V[(V["Sexo"] != "SIN DATO")]
sexo_edad = vic.pivot_table(index="RangoEtario", columns="Sexo", values="CantVictimas", aggfunc="sum", fill_value=0)
sexo_edad.to_csv(os.path.join(M, "victimas_sexo_edad.csv"), encoding="utf-8-sig")
fallec_sexo_edad = V[V["GravedadKey"] == 3].pivot_table(index="RangoEtario", columns="Sexo", values="CantVictimas", aggfunc="sum", fill_value=0)
fallec_sexo_edad.to_csv(os.path.join(M, "fallecidos_sexo_edad.csv"), encoding="utf-8-sig")
R["victimas_sexo_edad"] = sexo_edad.reset_index().to_dict(orient="records")
R["fallecidos_sexo_edad"] = fallec_sexo_edad.reset_index().to_dict(orient="records")
R["fallecidos_por_vehiculo"] = V[V["GravedadKey"] == 3].groupby("Vehiculo")["CantVictimas"].sum().sort_values(ascending=False).to_dict()

# ---------- graficos descriptivos
fig, ax = plt.subplots(figsize=(9, 4.2))
x = anual.index.astype(str)
ax.bar(x, anual["Total"], color=AZUL, width=0.6)
for i, val in enumerate(anual["Total"]):
    ax.text(i, val + 150, fmt_miles(val), ha="center", fontsize=9, color=INK2)
ax.yaxis.set_major_formatter(mtick.FuncFormatter(fmt_miles)); ax.grid(axis="x", visible=False)
ax.set_title("Siniestros viales por año en CABA (2019-2025)")
guardar(fig, os.path.join(G, "03_siniestros_por_anio.png"))

fig, ax = plt.subplots(figsize=(9, 4.2))
ax.bar(x, anual["VictimasMortales"], color=CRITICO, width=0.6)
for i, val in enumerate(anual["VictimasMortales"]):
    ax.text(i, val + 1.5, str(int(val)), ha="center", fontsize=9, color=INK2)
ax.grid(axis="x", visible=False); ax.set_title("Víctimas fatales por año")
guardar(fig, os.path.join(G, "04_victimas_fatales_por_anio.png"))

t = tabs["comuna"].drop("SIN DATO", errors="ignore").sort_values("Siniestros")
fig, axs = plt.subplots(1, 2, figsize=(11, 5.2), sharey=True)
axs[0].barh(t.index, t["Siniestros"], color=AZUL, height=0.65); axs[0].set_title("Siniestros por comuna")
axs[0].xaxis.set_major_formatter(mtick.FuncFormatter(fmt_miles))
axs[1].barh(t.index, t["PctGraveMortal"], color=NARANJA, height=0.65); axs[1].set_title("% graves o mortales")
axs[1].xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
for a in axs: a.grid(axis="y", visible=False)
guardar(fig, os.path.join(G, "05_comunas.png"))

hora = S[S["HoraKey"] >= 0].groupby("HoraKey").agg(n=("CantSiniestros", "sum"), g=("GraveMortal", "mean"))
fig, axs = plt.subplots(2, 1, figsize=(10, 6.2), sharex=True)
axs[0].bar(hora.index, hora["n"], color=AZUL, width=0.75); axs[0].set_title("Siniestros por hora del día")
axs[0].yaxis.set_major_formatter(mtick.FuncFormatter(fmt_miles))
axs[1].plot(hora.index, hora["g"] * 100, color=CRITICO, marker="o", markersize=5)
axs[1].set_title("% de siniestros graves o mortales por hora"); axs[1].yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
axs[1].set_xticks(range(0, 24)); axs[1].set_xlabel("Hora")
for a in axs: a.grid(axis="x", visible=False)
guardar(fig, os.path.join(G, "06_hora.png"))

vv = tabs["vehiculo_victima"].drop("SIN DATO", errors="ignore").sort_values("Siniestros")
fig, axs = plt.subplots(1, 2, figsize=(11, 4.8), sharey=True)
axs[0].barh(vv.index, vv["Siniestros"], color=AZUL, height=0.65); axs[0].set_title("Siniestros según vehículo de la víctima")
axs[0].xaxis.set_major_formatter(mtick.FuncFormatter(fmt_miles))
axs[1].barh(vv.index, vv["PctGraveMortal"], color=NARANJA, height=0.65); axs[1].set_title("% graves o mortales")
axs[1].xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
for a in axs: a.grid(axis="y", visible=False)
guardar(fig, os.path.join(G, "07_vehiculo_victima.png"))

dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
hm = S[S["HoraKey"] >= 0].pivot_table(index="DiaSemanaNombre", columns="HoraKey", values="CantSiniestros", aggfunc="sum").loc[dias]
fig, ax = plt.subplots(figsize=(11, 3.8))
from matplotlib.colors import LinearSegmentedColormap
cmap = LinearSegmentedColormap.from_list("seq", SEQ_AZUL)
im = ax.imshow(hm.values, aspect="auto", cmap=cmap)
ax.set_yticks(range(7)); ax.set_yticklabels(["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"])
ax.set_xticks(range(24)); ax.set_xticklabels(range(24)); ax.grid(False); ax.set_xlabel("Hora")
cb = fig.colorbar(im, ax=ax, fraction=0.025); cb.outline.set_visible(False); cb.set_label("Siniestros", color=INK2)
ax.set_title("Mapa de calor: siniestros por día de la semana y hora")
guardar(fig, os.path.join(G, "08_heatmap_dia_hora.png"))

se = sexo_edad.drop("SIN DATO", errors="ignore")
fig, ax = plt.subplots(figsize=(9, 4.2))
xi = np.arange(len(se.index)); w = 0.38
ax.bar(xi - w / 2 - 0.01, se.get("Masculino", 0), w, color=AZUL, label="Masculino")
ax.bar(xi + w / 2 + 0.01, se.get("Femenino", 0), w, color=NARANJA, label="Femenino")
ax.set_xticks(xi); ax.set_xticklabels(se.index); ax.legend(); ax.grid(axis="x", visible=False)
ax.yaxis.set_major_formatter(mtick.FuncFormatter(fmt_miles)); ax.set_xlabel("Rango etario")
ax.set_title("Víctimas por sexo y rango etario (con dato informado)")
guardar(fig, os.path.join(G, "09_victimas_sexo_edad.png"))

# ============================================================ 1. SERIE DE TIEMPO / REGRESION
# Vista minable para regresion (como se vio en clase): vector tiempo + vector dato
men = S.groupby("AnioMes").agg(Siniestros=("CantSiniestros", "sum"), Victimas=("TotalVictimas", "sum"),
                                Mortales=("VictimasMortales", "sum"), GraveMortal=("GraveMortal", "sum")).reset_index()
men["Acumulado"] = men["Siniestros"].cumsum()
men["IndiceBase100"] = men["Siniestros"] / men.loc[0, "Siniestros"] * 100
men["IndiceAcumulado"] = men["Acumulado"] / men.loc[0, "Siniestros"] * 100
men["VarMensualPct"] = men["Siniestros"].pct_change() * 100
men["VarInteranualPct"] = men["Siniestros"].pct_change(12) * 100
men["MortalesAcumulado"] = men["Mortales"].cumsum()
men["t"] = np.arange(1, len(men) + 1)
men.to_csv(os.path.join(M, "serie_mensual.csv"), index=False, encoding="utf-8-sig")

fig, ax = plt.subplots(figsize=(11, 4.4))
ax.plot(range(len(men)), men["IndiceBase100"], color=AZUL)
ax.axhline(100, color=BASE, lw=1, ls="--")
ax.text(1, 103, "Base enero 2019 = 100", color=INK2, fontsize=8.5)
ax.set_xticks(range(0, len(men), 6)); ax.set_xticklabels(men["AnioMes"][::6], rotation=45, ha="right")
i_min = men["IndiceBase100"].idxmin(); i_max = men["IndiceBase100"].idxmax()
for i in (i_min, i_max):
    ax.plot(i, men.loc[i, "IndiceBase100"], "o", color=AZUL, markersize=7, mec=SURFACE, mew=2)
    ax.annotate(f"{men.loc[i, 'AnioMes']}: {men.loc[i, 'IndiceBase100']:.1f}", (i, men.loc[i, "IndiceBase100"]),
                textcoords="offset points", xytext=(8, -4), fontsize=8.5, color=INK2)
ax.grid(axis="x", visible=False)
ax.set_title("Número índice mensual de siniestros (base enero 2019 = 100)")
guardar(fig, os.path.join(G, "01_indice_base100.png"))

fig, ax = plt.subplots(figsize=(11, 4.4))
ax.fill_between(range(len(men)), men["Acumulado"], color="#cde2fb")
ax.plot(range(len(men)), men["Acumulado"], color=AZUL)
ax.set_xticks(range(0, len(men), 6)); ax.set_xticklabels(men["AnioMes"][::6], rotation=45, ha="right")
ax.yaxis.set_major_formatter(mtick.FuncFormatter(fmt_miles)); ax.grid(axis="x", visible=False)
ax.annotate(f"{fmt_miles(men['Acumulado'].iloc[-1])} siniestros", (len(men) - 1, men["Acumulado"].iloc[-1]),
            textcoords="offset points", xytext=(-110, 0), fontsize=9, color=INK2)
ax.set_title("Siniestros acumulados mes a mes (valor acumulable)")
guardar(fig, os.path.join(G, "02_acumulado.png"))

# Regresion lineal de tendencia (excluye meses de ASPO como valores atipicos explicados)
aspo = men["AnioMes"].between("2020-03", "2020-11")
lr = LinearRegression().fit(men.loc[~aspo, ["t"]], men.loc[~aspo, "Siniestros"])
r2 = lr.score(men.loc[~aspo, ["t"]], men.loc[~aspo, "Siniestros"])
slope_p = stats.linregress(men.loc[~aspo, "t"], men.loc[~aspo, "Siniestros"]).pvalue
R["regresion"] = {"pendiente_mensual": float(lr.coef_[0]), "intercepto": float(lr.intercept_), "r2": float(r2),
                  "p_valor": float(slope_p), "aumento_anual_estimado": float(lr.coef_[0] * 12)}
# descomposicion estacional
serie = pd.Series(men["Siniestros"].values, index=pd.to_datetime(men["AnioMes"] + "-01"))
dec = seasonal_decompose(serie, model="additive", period=12)
estac = dec.seasonal.groupby(dec.seasonal.index.month).mean()
R["estacionalidad"] = {int(k): float(v) for k, v in estac.items()}
fig, axs = plt.subplots(4, 1, figsize=(10, 8.5), sharex=True)
for a, (nom, comp, c) in zip(axs, [("Serie observada", dec.observed, AZUL), ("Tendencia", dec.trend, AZUL),
                                   ("Estacionalidad", dec.seasonal, VERDE), ("Residuo", dec.resid, MUTED)]):
    if nom == "Residuo":
        a.bar(comp.index, comp.values, width=20, color=c)
    else:
        a.plot(comp.index, comp.values, color=c)
    a.set_title(nom, fontsize=10); a.grid(axis="x", visible=False)
axs[0].plot(serie.index[~aspo.values], lr.predict(men.loc[~aspo, ["t"]]), color=NARANJA, lw=1.5, ls="--", label="Regresión lineal (sin ASPO)")
axs[0].legend(loc="lower right", fontsize=8)
guardar(fig, os.path.join(G, "10_descomposicion_serie.png"))

# Holt-Winters: entrenamiento 2019-2024, prueba 2025, pronostico 2026
train, test = serie[:"2024-12"], serie["2025-01":]
hw = ExponentialSmoothing(train, trend="add", seasonal="add", seasonal_periods=12).fit(optimized=True)
pred_test = hw.forecast(len(test))
mape = float(np.mean(np.abs((test - pred_test) / test)) * 100)
naive = train[-12:].values  # modelo ingenuo: mismo mes del anio anterior
mape_naive = float(np.mean(np.abs((test.values - naive[:len(test)]) / test.values)) * 100)
hw_full = ExponentialSmoothing(serie, trend="add", seasonal="add", seasonal_periods=12).fit(optimized=True)
fc = hw_full.forecast(12)
resid_sd = float(np.std(hw_full.resid))
R["pronostico"] = {"mape_test_2025": mape, "mape_naive": mape_naive, "total_2026": float(fc.sum()),
                   "real_2025": float(test.sum()), "pred_2025": float(pred_test.sum()),
                   "mensual_2026": {d.strftime("%Y-%m"): float(v) for d, v in fc.items()}}
pd.DataFrame({"Mes": fc.index.strftime("%Y-%m"), "Pronostico": fc.values.round(0),
              "LimInf95": (fc.values - 1.96 * resid_sd).round(0), "LimSup95": (fc.values + 1.96 * resid_sd).round(0)}
             ).to_csv(os.path.join(M, "pronostico_2026.csv"), index=False, encoding="utf-8-sig")
pd.DataFrame({"Mes": test.index.strftime("%Y-%m"), "Real": test.values, "Pronosticado": pred_test.values.round(0)}
             ).to_csv(os.path.join(M, "validacion_2025.csv"), index=False, encoding="utf-8-sig")
fig, ax = plt.subplots(figsize=(11, 4.4))
ax.plot(serie.index, serie.values, color=AZUL, label="Real")
ax.plot(pred_test.index, pred_test.values, color=NARANJA, ls="--", label=f"Validación 2025 (MAPE {mape:.1f}%)")
ax.plot(fc.index, fc.values, color=VERDE, label="Pronóstico 2026")
ax.fill_between(fc.index, fc.values - 1.96 * resid_sd, fc.values + 1.96 * resid_sd, color=VERDE, alpha=0.12, lw=0)
ax.legend(loc="lower right"); ax.grid(axis="x", visible=False)
ax.set_title("Holt-Winters: validación 2025 y pronóstico 2026 de siniestros mensuales")
guardar(fig, os.path.join(G, "11_pronostico_holt_winters.png"))

# ============================================================ 2. CLASIFICACION (siniestro grave/mortal)
# Hallazgo de calidad: los registros con campos "SIN DATO" tienen una gravedad muy distinta (sesgo de registro).
completo = (S["VehiculoVictimaKey"] > 0) & (S["ContraparteKey"] > 0) & (S["ComunaKey"] > 0) & (S["TipoViaKey"] > 0) & (S["HoraKey"] >= 0)
R["sesgo_sin_dato"] = {"n_completos": int(completo.sum()), "n_incompletos": int((~completo).sum()),
                       "pct_gm_completos": float(S.loc[completo, "GraveMortal"].mean() * 100),
                       "pct_gm_incompletos": float(S.loc[~completo, "GraveMortal"].mean() * 100),
                       "pct_gm_vehiculo_sd": float(S.loc[S["VehiculoVictimaKey"] == 0, "GraveMortal"].mean() * 100),
                       "pct_gm_comuna_sd": float(S.loc[S["ComunaKey"] == 0, "GraveMortal"].mean() * 100)}
# Vista minable de clasificacion: solo casos completos (sin "SIN DATO") para que el modelo aprenda patrones reales
SM = S[completo].copy()
feats_cat = ["FranjaHoraria", "DiaSemanaNombre", "Estacion", "Comuna", "TipoVia", "VehiculoVictima", "Contraparte", "Contexto"]
Xc = SM[feats_cat + ["HoraKey", "TotalVictimas", "TipoDia"]].copy()
X = pd.get_dummies(Xc, columns=feats_cat + ["TipoDia"], drop_first=False).astype(float)
y = SM["GraveMortal"].values
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=SEED, stratify=y)
modelos = {
    "Arbol de decision": DecisionTreeClassifier(max_depth=6, min_samples_leaf=80, class_weight="balanced", random_state=SEED),
    "Random Forest": RandomForestClassifier(n_estimators=300, max_depth=12, min_samples_leaf=20, class_weight="balanced", n_jobs=-1, random_state=SEED),
    "Regresion logistica": LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5),
}
met = []; rocs = {}
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
for nom, mdl in modelos.items():
    mdl.fit(Xtr, ytr)
    p = mdl.predict_proba(Xte)[:, 1]; yp = (p >= 0.5).astype(int)
    cv = cross_val_score(mdl, X, y, cv=skf, scoring="roc_auc", n_jobs=-1)
    met.append({"Modelo": nom, "Accuracy": accuracy_score(yte, yp), "Precision": precision_score(yte, yp),
                "Recall": recall_score(yte, yp), "F1": f1_score(yte, yp), "AUC_test": roc_auc_score(yte, p),
                "AUC_CV5_media": cv.mean(), "AUC_CV5_desvio": cv.std()})
    rocs[nom] = roc_curve(yte, p)
met = pd.DataFrame(met); met.to_csv(os.path.join(M, "clasificacion_metricas.csv"), index=False, encoding="utf-8-sig")
R["clasificacion"] = met.round(4).to_dict(orient="records")
R["clasif_particion"] = {"train": int(len(Xtr)), "test": int(len(Xte)), "positivos_pct": float(y.mean() * 100)}
tree = modelos["Arbol de decision"]
cm = confusion_matrix(yte, tree.predict(Xte))
R["matriz_confusion_arbol"] = cm.tolist()
reglas_arbol = export_text(tree, feature_names=list(X.columns), max_depth=6)
open(os.path.join(M, "arbol_reglas.txt"), "w", encoding="utf-8").write(reglas_arbol)
rf = modelos["Random Forest"]
imp = pd.Series(rf.feature_importances_, index=X.columns)
# importancia agregada por variable original
def var_origen(c):
    for f in feats_cat + ["TipoDia"]:
        if c.startswith(f + "_"): return f
    return c
imp_ag = imp.groupby(imp.index.map(var_origen)).sum().sort_values(ascending=False)
imp_ag.to_csv(os.path.join(M, "importancia_variables_rf.csv"), encoding="utf-8-sig")
imp.sort_values(ascending=False).head(25).to_csv(os.path.join(M, "importancia_categorias_rf.csv"), encoding="utf-8-sig")
R["importancia_variables"] = (imp_ag * 100).round(2).to_dict()
R["importancia_top_categorias"] = (imp.sort_values(ascending=False).head(12) * 100).round(2).to_dict()
lg = modelos["Regresion logistica"]
odds = pd.Series(np.exp(lg.coef_[0]), index=X.columns).sort_values(ascending=False)
odds.to_csv(os.path.join(M, "regresion_logistica_odds.csv"), encoding="utf-8-sig")
R["odds_ratio_top"] = odds.head(10).round(2).to_dict()
R["odds_ratio_bottom"] = odds.tail(6).round(2).to_dict()

fig, ax = plt.subplots(figsize=(6.4, 5.4))
for (nom, (fpr, tpr, _)), c in zip(rocs.items(), [AZUL, NARANJA, AQUA]):
    ax.plot(fpr, tpr, color=c, label=f"{nom} (AUC {roc_auc_score(yte, modelos[nom].predict_proba(Xte)[:, 1]):.3f})")
ax.plot([0, 1], [0, 1], color=BASE, ls="--", lw=1)
ax.set_xlabel("Tasa de falsos positivos"); ax.set_ylabel("Tasa de verdaderos positivos (recall)")
ax.legend(loc="lower right", fontsize=8.5); ax.set_title("Curvas ROC - predicción de siniestro grave/mortal")
guardar(fig, os.path.join(G, "12_roc_clasificacion.png"))

fig, ax = plt.subplots(figsize=(5.2, 4.4))
ax.imshow(cm, cmap=cmap); ax.grid(False)
for i in range(2):
    for j in range(2):
        ax.text(j, i, fmt_miles(cm[i, j]), ha="center", va="center", fontsize=13,
                color="#ffffff" if cm[i, j] > cm.max() / 2 else INK)
ax.set_xticks([0, 1]); ax.set_xticklabels(["Predice leve", "Predice grave/mortal"])
ax.set_yticks([0, 1]); ax.set_yticklabels(["Real leve", "Real grave/mortal"])
ax.set_title("Matriz de confusión - Árbol de decisión")
guardar(fig, os.path.join(G, "13_matriz_confusion.png"))

ia = imp_ag.sort_values()
nombres = {"VehiculoVictima": "Vehículo de la víctima", "Contraparte": "Contraparte", "HoraKey": "Hora", "TotalVictimas": "Cantidad de víctimas",
           "TipoVia": "Tipo de vía", "Comuna": "Comuna", "FranjaHoraria": "Franja horaria", "DiaSemanaNombre": "Día de la semana",
           "Estacion": "Estación del año", "Contexto": "Contexto (pandemia)", "TipoDia": "Hábil / fin de semana"}
fig, ax = plt.subplots(figsize=(8, 4.6))
ax.barh([nombres.get(i, i) for i in ia.index], ia.values * 100, color=AZUL, height=0.65)
ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0)); ax.grid(axis="y", visible=False)
ax.set_title("Importancia de variables (Random Forest)")
guardar(fig, os.path.join(G, "14_importancia_variables.png"))

tree_small = DecisionTreeClassifier(max_depth=3, min_samples_leaf=200, class_weight="balanced", random_state=SEED).fit(Xtr, ytr)
fig, ax = plt.subplots(figsize=(15, 6.5))
plot_tree(tree_small, feature_names=list(X.columns), class_names=["Leve", "Grave/Mortal"], filled=True, rounded=True,
          fontsize=8, impurity=False, proportion=True, ax=ax, precision=2)
ax.set_title("Árbol de decisión (profundidad 3, vista simplificada)")
guardar(fig, os.path.join(G, "15_arbol_decision.png"))
open(os.path.join(M, "arbol_reglas_simplificado.txt"), "w", encoding="utf-8").write(export_text(tree_small, feature_names=list(X.columns)))
R["arbol_simple_reglas"] = export_text(tree_small, feature_names=list(X.columns))

# ---------- 2b. Perfil de victima fatal (victimas con sexo y edad informados)
VV = V[(V["SexoKey"] > 0) & V["Edad"].notna() & (V["TipoViaKey"] > 0) & (V["VehiculoKey"] > 0) & (V["HoraKey"] >= 0)].copy()
VV["Fallecio"] = (VV["GravedadKey"] == 3).astype(int)
Xv = pd.get_dummies(VV[["Edad", "HoraKey", "Sexo", "Vehiculo", "TipoVia", "FranjaHoraria", "TipoDia", "Zona"]],
                    columns=["Sexo", "Vehiculo", "TipoVia", "FranjaHoraria", "TipoDia", "Zona"]).astype(float)
yv = VV["Fallecio"].values
Xvtr, Xvte, yvtr, yvte = train_test_split(Xv, yv, test_size=0.3, random_state=SEED, stratify=yv)
tv_ = DecisionTreeClassifier(max_depth=5, min_samples_leaf=50, class_weight="balanced", random_state=SEED).fit(Xvtr, yvtr)
pv = tv_.predict_proba(Xvte)[:, 1]; ypv = (pv >= 0.5).astype(int)
R["victima_fatal"] = {"n": int(len(VV)), "fallecidos": int(yv.sum()), "auc": float(roc_auc_score(yvte, pv)),
                      "recall": float(recall_score(yvte, ypv)), "precision": float(precision_score(yvte, ypv)),
                      "accuracy": float(accuracy_score(yvte, ypv)),
                      "importancia": (pd.Series(tv_.feature_importances_, index=Xv.columns).sort_values(ascending=False).head(8) * 100).round(2).to_dict(),
                      "edad_media_fallecidos": float(VV.loc[VV["Fallecio"] == 1, "Edad"].mean()),
                      "edad_media_resto": float(VV.loc[VV["Fallecio"] == 0, "Edad"].mean()),
                      "tasa_letalidad_por_vehiculo": (VV.groupby("Vehiculo")["Fallecio"].mean() * 100).round(2).sort_values(ascending=False).to_dict(),
                      "tasa_letalidad_por_rango": (VV.groupby("RangoEtario")["Fallecio"].mean() * 100).round(2).to_dict(),
                      "tasa_letalidad_por_sexo": (VV.groupby("Sexo")["Fallecio"].mean() * 100).round(2).to_dict()}
open(os.path.join(M, "arbol_victima_fatal_reglas.txt"), "w", encoding="utf-8").write(export_text(tv_, feature_names=list(Xv.columns)))
let = VV.groupby("RangoEtario")["Fallecio"].mean() * 100
fig, ax = plt.subplots(figsize=(9, 4))
ax.bar(let.index, let.values, color=CRITICO, width=0.6)
for i, val in enumerate(let.values): ax.text(i, val + 0.05, f"{val:.2f}%", ha="center", fontsize=9, color=INK2)
ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=1)); ax.grid(axis="x", visible=False)
ax.set_title("Letalidad: % de víctimas que fallecen según rango etario"); ax.set_xlabel("Rango etario")
guardar(fig, os.path.join(G, "16_letalidad_edad.png"))

# ============================================================ 3. AGRUPAMIENTO
# 3a. K-Means de comunas - vista minable: 1 fila por comuna, perfil porcentual
SC = S[S["ComunaKey"] > 0]
anios = SC["Anio"].nunique()
perfil = pd.DataFrame({
    "SiniestrosAnuales": SC.groupby("Comuna")["CantSiniestros"].sum() / anios,
    "PctMoto": SC.groupby("Comuna")["VehiculoVictima"].apply(lambda s: (s == "MOTO").mean() * 100),
    "PctPeaton": SC.groupby("Comuna")["VehiculoVictima"].apply(lambda s: (s == "PEATON").mean() * 100),
    "PctBicicleta": SC.groupby("Comuna")["VehiculoVictima"].apply(lambda s: (s == "BICICLETA").mean() * 100),
    "PctNocturno": SC.groupby("Comuna")["Luz"].apply(lambda s: (s == "Nocturno (20-06)").mean() * 100),
    "PctFinde": SC.groupby("Comuna")["TipoDia"].apply(lambda s: (s == "Fin de semana").mean() * 100),
    "PctViaRapida": SC.groupby("Comuna")["CategoriaVia"].apply(lambda s: (s == "Via rapida").mean() * 100),
    "PctTransportePesado": SC.groupby("Comuna")["CatContraparte"].apply(lambda s: (s == "Vehiculo pesado").mean() * 100),
    "PctGraveMortal": SC.groupby("Comuna")["GraveMortal"].mean() * 100,
})
Z = StandardScaler().fit_transform(perfil)
inercias, sils = {}, {}
for k in range(2, 8):
    km = KMeans(n_clusters=k, n_init=50, random_state=SEED).fit(Z)
    inercias[k] = float(km.inertia_); sils[k] = float(silhouette_score(Z, km.labels_))
K = 4
km = KMeans(n_clusters=K, n_init=50, random_state=SEED).fit(Z)
perfil["Cluster"] = km.labels_
# nombrar clusters por su rasgo dominante
cent = perfil.groupby("Cluster").mean()
glob = perfil.drop(columns="Cluster").mean()
nombres_cl = {}
ETQ = {"SiniestrosAnuales": "alto volumen", "PctMoto": "motos", "PctPeaton": "peatones", "PctBicicleta": "ciclistas",
       "PctNocturno": "nocturnidad", "PctFinde": "fin de semana", "PctViaRapida": "vías rápidas",
       "PctTransportePesado": "transporte pesado", "PctGraveMortal": "gravedad"}
for c, row in cent.iterrows():
    z = (row - glob) / perfil.drop(columns="Cluster").std()
    top2 = z.sort_values(ascending=False).index[:2]
    nombres_cl[c] = f"C{c + 1}: " + " + ".join(ETQ[t] for t in top2)
R["kmeans_z_centroides"] = ((cent - glob) / perfil.drop(columns="Cluster").std()).round(2).to_dict(orient="index")
perfil["Perfil"] = perfil["Cluster"].map(nombres_cl)
perfil.round(2).to_csv(os.path.join(M, "clusters_comunas.csv"), encoding="utf-8-sig")
cent.round(2).to_csv(os.path.join(M, "clusters_centroides.csv"), encoding="utf-8-sig")
R["kmeans"] = {"k": K, "inercias": inercias, "siluetas": sils,
               "asignacion": perfil["Perfil"].to_dict(),
               "centroides": cent.round(2).reset_index().assign(Perfil=lambda d: d["Cluster"].map(nombres_cl)).to_dict(orient="records")}
fig, axs = plt.subplots(1, 2, figsize=(10, 3.8))
axs[0].plot(list(inercias), list(inercias.values()), color=AZUL, marker="o", markersize=6); axs[0].set_title("Método del codo (inercia)")
axs[1].plot(list(sils), list(sils.values()), color=NARANJA, marker="o", markersize=6); axs[1].set_title("Coeficiente de silueta")
for a in axs: a.set_xlabel("k (cantidad de clusters)"); a.grid(axis="x", visible=False); a.axvline(K, color=BASE, ls="--", lw=1)
guardar(fig, os.path.join(G, "17_codo_silueta.png"))
pca = PCA(n_components=2, random_state=SEED).fit(Z); P = pca.transform(Z)
fig, ax = plt.subplots(figsize=(9, 5.6))
for c in range(K):
    m_ = perfil["Cluster"].values == c
    ax.scatter(P[m_, 0], P[m_, 1], s=110, color=SERIES[c], edgecolor=SURFACE, linewidth=2, label=nombres_cl[c], zorder=3)
for i, com in enumerate(perfil.index):
    ax.annotate(com.replace("Comuna ", "C"), (P[i, 0], P[i, 1]), textcoords="offset points", xytext=(7, 5), fontsize=8.5, color=INK2)
ax.set_xlabel(f"Componente principal 1 ({pca.explained_variance_ratio_[0]*100:.0f}% var.)")
ax.set_ylabel(f"Componente principal 2 ({pca.explained_variance_ratio_[1]*100:.0f}% var.)")
ax.legend(loc="best", fontsize=8.5); ax.set_title("K-Means: comunas agrupadas por perfil de siniestralidad (PCA)")
R["pca_varianza"] = [float(v) for v in pca.explained_variance_ratio_]
guardar(fig, os.path.join(G, "18_clusters_comunas.png"))
Lk = linkage(Z, method="ward")
fig, ax = plt.subplots(figsize=(10, 4.4))
dendrogram(Lk, labels=[c.replace("Comuna ", "C") for c in perfil.index], ax=ax, color_threshold=0.7 * Lk[:, 2].max(),
           above_threshold_color=MUTED)
ax.grid(False); ax.set_ylabel("Distancia (Ward)"); ax.set_title("Agrupamiento jerárquico de comunas (dendrograma)")
guardar(fig, os.path.join(G, "19_dendrograma.png"))

# 3b. DBSCAN: puntos negros (siniestros graves/mortales con coordenadas)
GG = S[(S["GraveMortal"] == 1) & S["Latitud"].notna()].copy()
coords = np.radians(GG[["Latitud", "Longitud"]].values)
db = DBSCAN(eps=0.12 / 6371.0, min_samples=6, metric="haversine", algorithm="ball_tree").fit(coords)
GG["Hotspot"] = db.labels_
hs = (GG[GG["Hotspot"] >= 0].groupby("Hotspot")
      .agg(Siniestros=("CantSiniestros", "sum"), Mortales=("VictimasMortales", "sum"), Lat=("Latitud", "mean"), Lon=("Longitud", "mean"),
           Comuna=("Comuna", lambda s: s.mode().iat[0]),
           Direccion=("Direccion", lambda s: s[s != "SIN DATO"].mode().iat[0] if (s != "SIN DATO").any() else "SIN DATO"),
           VehiculoPredominante=("VehiculoVictima", lambda s: s.mode().iat[0]))
      .sort_values("Siniestros", ascending=False))
hs.to_csv(os.path.join(M, "dbscan_puntos_negros.csv"), encoding="utf-8-sig")
R["dbscan"] = {"puntos": int(len(GG)), "clusters": int(hs.shape[0]), "ruido": int((db.labels_ == -1).sum()),
               "top": hs.head(12).round(5).reset_index().to_dict(orient="records")}
fig, ax = plt.subplots(figsize=(8, 7.4))
ax.scatter(GG["Longitud"], GG["Latitud"], s=3, color=BASE, alpha=0.6, label="Siniestro grave/mortal")
top10 = hs.head(10)
for rank, (hid, row) in enumerate(top10.iterrows(), start=1):
    pts = GG[GG["Hotspot"] == hid]
    ax.scatter(pts["Longitud"], pts["Latitud"], s=10, color=CRITICO, zorder=3)
    ax.annotate(str(rank), (row["Lon"], row["Lat"]), textcoords="offset points", xytext=(6, 6), fontsize=9, fontweight="bold", color=INK)
ax.scatter([], [], s=10, color=CRITICO, label="Puntos negros (top 10 DBSCAN)")
ax.set_aspect(1 / np.cos(np.radians(-34.61))); ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")
ax.legend(loc="lower left", fontsize=8.5); ax.set_title("DBSCAN: puntos negros de siniestros graves y mortales")
guardar(fig, os.path.join(G, "20_dbscan_puntos_negros.png"))

# ============================================================ 4. REGLAS DE ASOCIACION (Apriori)
# Vista minable: cada siniestro es una "transaccion" y cada caracteristica un "item" (tabla one-hot)
tx = pd.DataFrame({
    "Franja": "Franja=" + S["FranjaHoraria"].str.split(" ").str[1],
    "Dia": "Dia=" + S["TipoDia"],
    "Via": "Via=" + S["TipoVia"],
    "Victima": "Victima=" + S["VehiculoVictima"],
    "Contra": "Contraparte=" + S["Contraparte"],
    "Zona": "Zona=" + S["Zona"],
    "Grav": np.where(S["GraveMortal"] == 1, "Gravedad=GRAVE_O_MORTAL", "Gravedad=LEVE"),
})
onehot = pd.get_dummies(tx, prefix="", prefix_sep="").astype(bool)
onehot = onehot.loc[:, ~onehot.columns.str.contains("SIN DATO|SIN$|=SD", regex=True)]
onehot.astype(int).head(2000).to_csv(os.path.join(M, "vista_minable_asociacion_muestra.csv"), encoding="utf-8-sig")

def reglas(min_sup, max_len=3):
    fi = apriori(onehot, min_support=min_sup, use_colnames=True, max_len=max_len)
    try:
        rr = association_rules(fi, metric="lift", min_threshold=1.0, num_itemsets=len(onehot))
    except TypeError:
        rr = association_rules(fi, metric="lift", min_threshold=1.0)
    rr["antecedentes"] = rr["antecedents"].apply(lambda s: " + ".join(sorted(s)))
    rr["consecuentes"] = rr["consequents"].apply(lambda s: " + ".join(sorted(s)))
    return fi, rr
fi, rr = reglas(0.002, 4)
R["apriori_itemsets"] = int(len(fi))
gen = rr[(rr["support"] >= 0.03) & (rr["confidence"] >= 0.5) & (rr["lift"] >= 1.15) & (rr["consequents"].apply(len) == 1)
         & ~rr["consecuentes"].str.contains("Gravedad=LEVE")].sort_values("lift", ascending=False)
gen = gen.drop_duplicates(subset=["support", "confidence", "lift"]).head(20)
gm = rr[(rr["consecuentes"] == "Gravedad=GRAVE_O_MORTAL") & (rr["support"] >= 0.002)].sort_values("lift", ascending=False)
gm = gm.drop_duplicates(subset=["support", "confidence", "lift"]).head(20)
cols = ["antecedentes", "consecuentes", "support", "confidence", "lift", "leverage", "conviction"]
gen[cols].round(4).to_csv(os.path.join(M, "reglas_generales.csv"), index=False, encoding="utf-8-sig")
gm[cols].round(4).to_csv(os.path.join(M, "reglas_grave_mortal.csv"), index=False, encoding="utf-8-sig")
R["reglas_generales"] = gen[cols].round(4).to_dict(orient="records")
R["reglas_grave_mortal"] = gm[cols].round(4).to_dict(orient="records")
R["base_grave_mortal"] = float(S["GraveMortal"].mean())
fig, ax = plt.subplots(figsize=(9, 5.2))
base = rr[rr["consequents"].apply(len) == 1]
sc = ax.scatter(base["support"] * 100, base["confidence"] * 100, c=base["lift"], cmap=cmap, s=10, alpha=0.7, vmin=0.8, vmax=3)
ax.scatter(gm["support"] * 100, gm["confidence"] * 100, s=40, facecolor="none", edgecolor=CRITICO, lw=1.5, label="→ Grave o mortal (top 20)")
cb = fig.colorbar(sc, ax=ax, fraction=0.03); cb.set_label("Lift", color=INK2); cb.outline.set_visible(False)
ax.set_xscale("log"); ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=1))
ax.set_xlabel("Soporte (escala log.)"); ax.set_ylabel("Confianza"); ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
ax.legend(loc="lower right", fontsize=8.5); ax.set_title(f"Apriori: {len(base):,} reglas según soporte, confianza y lift".replace(",", "."))
guardar(fig, os.path.join(G, "21_reglas_asociacion.png"))

# ============================================================ 5. DETECCION DE ANOMALIAS
dia = S.groupby("Fecha").agg(Siniestros=("CantSiniestros", "sum"), Mortales=("VictimasMortales", "sum"),
                             GraveMortal=("GraveMortal", "sum")).reindex(T["Fecha"], fill_value=0)
dia.index.name = "Fecha"
dia = dia.reset_index().merge(T[["Fecha", "Anio", "MesNumero", "DiaSemanaNombre", "TipoDia", "Contexto"]], on="Fecha")
# esperado = media movil centrada de 28 dias ajustada por dia de semana
dia["Fecha_dt"] = pd.to_datetime(dia["Fecha"])
dia["MediaMovil28"] = dia["Siniestros"].rolling(28, center=True, min_periods=7).mean()
fdia = dia.groupby("DiaSemanaNombre")["Siniestros"].mean() / dia["Siniestros"].mean()
dia["Esperado"] = dia["MediaMovil28"] * dia["DiaSemanaNombre"].map(fdia)
dia["Residuo"] = dia["Siniestros"] - dia["Esperado"]
mu, sd = dia["Residuo"].mean(), dia["Residuo"].std()
dia["Z"] = (dia["Residuo"] - mu) / sd
dia["AnomaliaGauss"] = np.where(dia["Z"] > 3, "ALTA", np.where(dia["Z"] < -3, "BAJA", ""))
iso = IsolationForest(contamination=0.01, random_state=SEED)
feat_iso = dia[["Siniestros", "Mortales", "GraveMortal", "Residuo"]].fillna(0)
dia["AnomaliaIsolationForest"] = np.where(iso.fit_predict(feat_iso) == -1, "SI", "")
dia["ScoreIF"] = -iso.score_samples(feat_iso)
anom = dia[(dia["AnomaliaGauss"] != "") | (dia["AnomaliaIsolationForest"] != "")].sort_values("Z", key=np.abs, ascending=False)
anom.drop(columns=["Fecha_dt"]).round(3).to_csv(os.path.join(M, "anomalias_diarias.csv"), index=False, encoding="utf-8-sig")
dia.drop(columns=["Fecha_dt"]).round(3).to_csv(os.path.join(M, "serie_diaria.csv"), index=False, encoding="utf-8-sig")
R["anomalias"] = {"mu": float(mu), "sd": float(sd), "n_altas": int((dia["AnomaliaGauss"] == "ALTA").sum()),
                  "n_bajas": int((dia["AnomaliaGauss"] == "BAJA").sum()), "n_if": int((dia["AnomaliaIsolationForest"] == "SI").sum()),
                  "top": anom.head(15)[["Fecha", "DiaSemanaNombre", "Siniestros", "Esperado", "Z", "Mortales", "AnomaliaGauss", "AnomaliaIsolationForest"]]
                  .round(2).to_dict(orient="records"),
                  "dias_con_mas_mortales": dia.sort_values("Mortales", ascending=False).head(5)[["Fecha", "DiaSemanaNombre", "Mortales", "Siniestros"]].to_dict(orient="records")}
fig, ax = plt.subplots(figsize=(9, 4.4))
res = dia["Residuo"].dropna()
ax.hist(res, bins=60, color="#9ec5f4", density=True, edgecolor=SURFACE, linewidth=0.5)
xs = np.linspace(res.min(), res.max(), 300)
ax.plot(xs, stats.norm.pdf(xs, mu, sd), color=AZUL, label="Campana de Gauss ajustada")
for k in (-3, 3):
    ax.axvline(mu + k * sd, color=CRITICO, ls="--", lw=1.2)
ax.text(mu + 3 * sd, ax.get_ylim()[1] * 0.9, "  +3σ", color=CRITICO, fontsize=9)
ax.text(mu - 3 * sd, ax.get_ylim()[1] * 0.9, "-3σ  ", color=CRITICO, fontsize=9, ha="right")
ax.legend(loc="upper left", fontsize=8.5); ax.grid(axis="x", visible=False)
ax.set_xlabel("Residuo diario (siniestros observados - esperados)")
ax.set_title("Detección de anomalías: distribución de residuos diarios")
guardar(fig, os.path.join(G, "22_anomalias_gauss.png"))
fig, ax = plt.subplots(figsize=(11, 4.2))
ax.plot(dia["Fecha_dt"], dia["Siniestros"], color="#9ec5f4", lw=0.8, label="Siniestros diarios")
ax.plot(dia["Fecha_dt"], dia["Esperado"], color=AZUL, lw=1.5, label="Esperado (media móvil × día)")
al = dia[dia["AnomaliaGauss"] == "ALTA"]; ba = dia[dia["AnomaliaGauss"] == "BAJA"]
ax.scatter(al["Fecha_dt"], al["Siniestros"], color=CRITICO, s=24, zorder=3, label="Anomalía alta (z > 3)")
ax.scatter(ba["Fecha_dt"], ba["Siniestros"], color=VIOLETA, s=24, zorder=3, label="Anomalía baja (z < -3)")
ax.legend(loc="upper left", fontsize=8, ncol=2); ax.grid(axis="x", visible=False)
ax.set_title("Serie diaria de siniestros y días anómalos detectados")
guardar(fig, os.path.join(G, "23_anomalias_serie.png"))

# ============================================================ 6. CORRELACION
mc = S.groupby("AnioMes").agg(Siniestros=("CantSiniestros", "sum"), Victimas=("TotalVictimas", "sum"),
                               Graves=("VictimasGraves", "sum"), Mortales=("VictimasMortales", "sum"),
                               Motos=("VehiculoVictima", lambda s: (s == "MOTO").sum()),
                               Peatones=("VehiculoVictima", lambda s: (s == "PEATON").sum()),
                               Bicicletas=("VehiculoVictima", lambda s: (s == "BICICLETA").sum()),
                               Nocturnos=("Luz", lambda s: (s == "Nocturno (20-06)").sum()),
                               FinDeSemana=("TipoDia", lambda s: (s == "Fin de semana").sum()))
corr = mc.corr(method="pearson"); corr_s = mc.corr(method="spearman")
corr.round(3).to_csv(os.path.join(M, "correlacion_pearson_mensual.csv"), encoding="utf-8-sig")
corr_s.round(3).to_csv(os.path.join(M, "correlacion_spearman_mensual.csv"), encoding="utf-8-sig")
R["correlacion_mensual"] = corr.round(3).to_dict()
hr = S[S["HoraKey"] >= 0].groupby("HoraKey").agg(n=("CantSiniestros", "sum"), g=("GraveMortal", "mean"))
rp, pp = stats.pearsonr(hr["n"], hr["g"]); rs, ps = stats.spearmanr(hr["n"], hr["g"])
co = SC.groupby("Comuna").agg(n=("CantSiniestros", "sum"), g=("GraveMortal", "mean"),
                               vr=("CategoriaVia", lambda s: (s == "Via rapida").mean()))
rc, pc = stats.pearsonr(co["vr"], co["g"])
R["correlacion_hora"] = {"pearson": float(rp), "p": float(pp), "spearman": float(rs), "p_s": float(ps)}
R["correlacion_viarapida_gravedad_comuna"] = {"pearson": float(rc), "p": float(pc)}
div = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"])
fig, ax = plt.subplots(figsize=(8.4, 6.6))
im = ax.imshow(corr.values, cmap=div, vmin=-1, vmax=1); ax.grid(False)
lbl = list(corr.columns)
ax.set_xticks(range(len(lbl))); ax.set_xticklabels(lbl, rotation=45, ha="right"); ax.set_yticks(range(len(lbl))); ax.set_yticklabels(lbl)
for i in range(len(lbl)):
    for j in range(len(lbl)):
        ax.text(j, i, f"{corr.values[i, j]:.2f}", ha="center", va="center", fontsize=8, color=INK)
cb = fig.colorbar(im, ax=ax, fraction=0.04); cb.outline.set_visible(False)
ax.set_title("Matriz de correlación de Pearson (variables mensuales)")
guardar(fig, os.path.join(G, "24_correlacion.png"))
fig, ax = plt.subplots(figsize=(7.6, 5))
ax.scatter(hr["n"], hr["g"] * 100, s=60, color=AZUL, edgecolor=SURFACE, linewidth=2, zorder=3)
for hh_, row in hr.iterrows():
    ax.annotate(f"{hh_}h", (row["n"], row["g"] * 100), textcoords="offset points", xytext=(5, 4), fontsize=8, color=INK2)
b1, b0 = np.polyfit(hr["n"], hr["g"] * 100, 1); xs = np.linspace(hr["n"].min(), hr["n"].max(), 50)
ax.plot(xs, b0 + b1 * xs, color=NARANJA, ls="--", lw=1.5)
ax.xaxis.set_major_formatter(mtick.FuncFormatter(fmt_miles)); ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
ax.set_xlabel("Cantidad de siniestros en esa hora"); ax.set_ylabel("% graves o mortales")
ax.set_title(f"Correlación negativa volumen vs. gravedad por hora (r = {rp:.2f})")
guardar(fig, os.path.join(G, "25_correlacion_hora.png"))

with open(os.path.join(M, "resultados.json"), "w", encoding="utf-8") as f:
    json.dump(R, f, indent=1, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
print(json.dumps({k: R[k] for k in ["kpi", "regresion", "pronostico", "clasificacion", "victima_fatal", "kmeans", "anomalias", "correlacion_hora",
                                    "correlacion_viarapida_gravedad_comuna", "importancia_variables", "odds_ratio_top", "estacionalidad"]},
                 indent=1, ensure_ascii=False, default=str)[:12000])
print("REGLAS GM:", json.dumps(R["reglas_grave_mortal"][:10], ensure_ascii=False, indent=0))
print("REGLAS GEN:", json.dumps(R["reglas_generales"][:10], ensure_ascii=False, indent=0))
print("DBSCAN:", json.dumps(R["dbscan"]["top"][:10], ensure_ascii=False, indent=0, default=str))
print("ANUAL:", json.dumps(R["anual"], default=str))
print(R["arbol_simple_reglas"])
