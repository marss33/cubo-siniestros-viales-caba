"""
01_etl.py - Extraccion, Transformacion y Carga (ETL) a modelo estrella.
Fuente: Portal de Datos Abiertos GCBA - "Siniestros viales" (Secretaria de Transporte,
Observatorio de Movilidad y Seguridad Vial). Archivos: hechos (1 fila = 1 siniestro)
y victimas (1 fila = 1 victima).
Salida: datos_limpios/*.csv  (dimensiones + 2 tablas de hechos), listos para SQL Server.
Uso: python 01_etl.py <carpeta_del_proyecto>
"""
import sys, os, re, json
import numpy as np
import pandas as pd

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "datos_originales")
OUT = os.path.join(ROOT, "datos_limpios")
os.makedirs(OUT, exist_ok=True)

log = {}  # registro de calidad de datos para el informe

h = pd.read_csv(os.path.join(SRC, "siniestros_viales_hechos.csv"), sep=";", encoding="utf-8", dtype=str)
v = pd.read_csv(os.path.join(SRC, "siniestros_viales_victimas.csv"), sep=";", encoding="utf-8", dtype=str)
log["filas_hechos_origen"] = len(h)
log["filas_victimas_origen"] = len(v)

SD = "SIN DATO"

def norm_txt(s):
    s = s.fillna(SD).astype(str).str.strip().str.upper()
    s = s.replace({"SD": SD, "#¡REF!": SD, "#�REF!": SD, "": SD, "NAN": SD})
    s = s.where(~s.str.contains("REF!", regex=False), SD)
    return s

# ---------------------------------------------------------------- HECHOS
h["fecha"] = pd.to_datetime(h["fecha_siniestro"], errors="coerce")
log["hechos_fecha_invalida"] = int(h["fecha"].isna().sum())
h = h[h["fecha"].notna()].copy()

# Comuna: viene como "Comuna 1", "1", "COMUNA 1", "SD" o vacio -> entero 1..15, 0 = sin dato
def comuna_num(x):
    if pd.isna(x):
        return 0
    m = re.search(r"(\d+)", str(x))
    n = int(m.group(1)) if m else 0
    return n if 1 <= n <= 15 else 0
h["ComunaKey"] = h["comuna_siniestro"].map(comuna_num)
log["hechos_comuna_formatos_distintos"] = int(h["comuna_siniestro"].nunique())
log["hechos_comuna_sin_dato"] = int((h["ComunaKey"] == 0).sum())

# Hora: se toma del campo hora (HH:MM:SS); si falta, del rango_horario. -1 = sin dato
hh = pd.to_numeric(h["hora_siniestro"].str.slice(0, 2), errors="coerce")
hh = hh.fillna(pd.to_numeric(h["rango_horario"], errors="coerce"))
h["HoraKey"] = hh.where(hh.between(0, 23), -1).fillna(-1).astype(int)
log["hechos_hora_sin_dato"] = int((h["HoraKey"] == -1).sum())

# Tipo de via
TIPO_VIA = {"AVENIDA": 1, "CALLE": 2, "AV. GRAL. PAZ": 3, "AUTOPISTA": 4}
tv = norm_txt(h["tipo_de_via_siniestro"])
h["TipoViaKey"] = tv.map(TIPO_VIA).fillna(0).astype(int)
log["hechos_tipo_via_sin_dato"] = int((h["TipoViaKey"] == 0).sum())

# Vehiculos (modo de desplazamiento de la victima y contraparte) - catalogo unificado
VEH_NORMAL = {"CAMIONETA": "UTILITARIO"}
h["veh_victima"] = norm_txt(h["modo_desplazamiento_victima"]).replace(VEH_NORMAL)
h["veh_contra"] = norm_txt(h["contraparte_siniestro"]).replace(VEH_NORMAL)

VEHICULOS = [
    # key, nombre, categoria, ruedas/peso
    (0, SD, "Sin dato"),
    (1, "PEATON", "Usuario vulnerable"),
    (2, "BICICLETA", "Usuario vulnerable"),
    (3, "MONOPATIN", "Usuario vulnerable"),
    (4, "MOTO", "Usuario vulnerable"),
    (5, "AUTO", "Vehiculo liviano"),
    (6, "TAXI", "Vehiculo liviano"),
    (7, "UTILITARIO", "Vehiculo liviano"),
    (8, "MOVIL", "Vehiculo liviano"),
    (9, "CAMION", "Vehiculo pesado"),
    (10, "TRANSPORTE PUBLICO", "Vehiculo pesado"),
    (11, "TREN", "Vehiculo pesado"),
    (12, "OBJETO FIJO", "Otros"),
    (13, "MULTIPLE", "Otros"),
    (14, "MIXTO", "Otros"),
    (15, "OTRO", "Otros"),
]
VEH_KEY = {n: k for k, n, _ in VEHICULOS}
for col, key in [("veh_victima", "VehiculoVictimaKey"), ("veh_contra", "ContraparteKey")]:
    desconocidos = set(h[col]) - set(VEH_KEY)
    if desconocidos:
        print("AVISO valores no catalogados ->OTRO:", col, desconocidos)
    h[key] = h[col].map(VEH_KEY).fillna(VEH_KEY["OTRO"]).astype(int)
log["hechos_vehiculo_victima_sin_dato"] = int((h["VehiculoVictimaKey"] == 0).sum())
log["hechos_contraparte_sin_dato"] = int((h["ContraparteKey"] == 0).sum())

GRAV = {"LEVE": 1, "GRAVE": 2, "MORTAL": 3}
h["GravedadKey"] = norm_txt(h["gravedad_siniestro"]).map(GRAV).astype(int)

for c in ["numero_victimas_leve_siniestro", "numero_victimas_grave_siniestro", "numero_victimas_mortal_siniestro"]:
    h[c] = pd.to_numeric(h[c], errors="coerce").fillna(0).astype(int)
tot = pd.to_numeric(h["numero_total_de_victimas"], errors="coerce")
suma = h["numero_victimas_leve_siniestro"] + h["numero_victimas_grave_siniestro"] + h["numero_victimas_mortal_siniestro"]
log["hechos_total_victimas_SD_recalculado"] = int(tot.isna().sum())
h["TotalVictimas"] = tot.fillna(suma).astype(int)
h.loc[h["TotalVictimas"] == 0, "TotalVictimas"] = 1  # todo siniestro registrado tiene al menos 1 victima

lat = pd.to_numeric(h["latitud_siniestro"].str.replace(",", "."), errors="coerce")
lon = pd.to_numeric(h["longitud_siniestro"].str.replace(",", "."), errors="coerce")
dentro = lat.between(-34.71, -34.52) & lon.between(-58.54, -58.33)  # caja de CABA
log["hechos_coordenadas_invalidas"] = int((~dentro).sum())
h["Latitud"] = lat.where(dentro).round(6)
h["Longitud"] = lon.where(dentro).round(6)

h["FechaKey"] = h["fecha"].dt.strftime("%Y%m%d").astype(int)

fact_sin = pd.DataFrame({
    "SiniestroID": h["id_siniestro"].str.strip(),
    "FechaKey": h["FechaKey"],
    "HoraKey": h["HoraKey"],
    "ComunaKey": h["ComunaKey"],
    "TipoViaKey": h["TipoViaKey"],
    "VehiculoVictimaKey": h["VehiculoVictimaKey"],
    "ContraparteKey": h["ContraparteKey"],
    "GravedadKey": h["GravedadKey"],
    "CantSiniestros": 1,
    "TotalVictimas": h["TotalVictimas"],
    "VictimasLeves": h["numero_victimas_leve_siniestro"],
    "VictimasGraves": h["numero_victimas_grave_siniestro"],
    "VictimasMortales": h["numero_victimas_mortal_siniestro"],
    "Latitud": h["Latitud"],
    "Longitud": h["Longitud"],
    "Direccion": h["direccion_normalizada_siniestro"].fillna(SD).str.strip(),
    "Participantes": norm_txt(h["participantes_siniestro"]),
})
assert fact_sin["SiniestroID"].is_unique

# ---------------------------------------------------------------- VICTIMAS
v = v[v["id_siniestro"].notna()].copy()
log["victimas_filas_vacias_eliminadas"] = log["filas_victimas_origen"] - len(v)
v["id_siniestro"] = v["id_siniestro"].str.strip()
v = v.merge(fact_sin[["SiniestroID", "FechaKey", "HoraKey", "ComunaKey", "TipoViaKey", "VehiculoVictimaKey", "ContraparteKey"]],
            left_on="id_siniestro", right_on="SiniestroID", how="inner")
log["victimas_huerfanas_eliminadas"] = log["filas_victimas_origen"] - log["victimas_filas_vacias_eliminadas"] - len(v)

veh_v = norm_txt(v["modo_desplazamiento_victima"]).replace(VEH_NORMAL)
v["VehKeyPropio"] = veh_v.map(VEH_KEY).fillna(VEH_KEY["OTRO"]).astype(int)
log["victimas_vehiculo_sin_dato_imputado_desde_hecho"] = int(((v["VehKeyPropio"] == 0) & (v["VehiculoVictimaKey"] != 0)).sum())
v["VehiculoKey"] = np.where(v["VehKeyPropio"] == 0, v["VehiculoVictimaKey"], v["VehKeyPropio"])

SEXO = {"M": 1, "F": 2}
v["SexoKey"] = norm_txt(v["sexo_victima"]).map(SEXO).fillna(0).astype(int)
edad = pd.to_numeric(v["edad_victima"], errors="coerce")
edad = edad.where(edad.between(0, 105))
log["victimas_edad_sin_dato"] = int(edad.isna().sum())
v["Edad"] = edad
bins = [-1, 14, 24, 34, 44, 54, 64, 200]
v["RangoEtarioKey"] = pd.cut(edad, bins=bins, labels=[1, 2, 3, 4, 5, 6, 7]).astype("float").fillna(0).astype(int)
v["GravedadKey"] = norm_txt(v["GRAVEdad_victima"]).map(GRAV).fillna(1).astype(int)
ROL = {"PEATON": 1, "CICLISTA": 2, "CONDUCTOR": 3, "PASAJERO": 4}
v["RolKey"] = norm_txt(v["rol_victima"]).map(ROL).fillna(0).astype(int)
v = v.reset_index(drop=True)
fact_vic = pd.DataFrame({
    "VictimaID": np.arange(1, len(v) + 1),
    "SiniestroID": v["id_siniestro"],
    "FechaKey": v["FechaKey"],
    "HoraKey": v["HoraKey"],
    "ComunaKey": v["ComunaKey"],
    "TipoViaKey": v["TipoViaKey"],
    "VehiculoKey": v["VehiculoKey"],
    "ContraparteKey": v["ContraparteKey"],
    "SexoKey": v["SexoKey"],
    "RangoEtarioKey": v["RangoEtarioKey"],
    "RolKey": v["RolKey"],
    "GravedadKey": v["GravedadKey"],
    "Edad": v["Edad"],
    "CantVictimas": 1,
    "CantFallecidos": (v["GravedadKey"] == 3).astype(int),
})

# ---------------------------------------------------------------- DIMENSIONES
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DIAS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
fechas = pd.date_range(f"{h['fecha'].dt.year.min()}-01-01", f"{h['fecha'].dt.year.max()}-12-31", freq="D")
def estacion(m):
    return {12: "Verano", 1: "Verano", 2: "Verano", 3: "Otono", 4: "Otono", 5: "Otono",
            6: "Invierno", 7: "Invierno", 8: "Invierno"}.get(m, "Primavera")
def contexto(d):
    if d < pd.Timestamp("2020-03-20"):
        return "1. Pre-pandemia"
    if d <= pd.Timestamp("2020-11-08"):
        return "2. ASPO (cuarentena)"
    return "3. Post-ASPO"
dim_tiempo = pd.DataFrame({
    "FechaKey": fechas.strftime("%Y%m%d").astype(int),
    "Fecha": fechas.strftime("%Y-%m-%d"),
    "Anio": fechas.year,
    "Semestre": np.where(fechas.month <= 6, 1, 2),
    "SemestreNombre": [f"{y} S{1 if m <= 6 else 2}" for y, m in zip(fechas.year, fechas.month)],
    "Trimestre": fechas.quarter,
    "TrimestreNombre": [f"{y} T{q}" for y, q in zip(fechas.year, fechas.quarter)],
    "MesNumero": fechas.month,
    "MesNombre": [MESES[m - 1] for m in fechas.month],
    "AnioMes": fechas.strftime("%Y-%m"),
    "AnioMesNombre": [f"{MESES[m-1]} {y}" for y, m in zip(fechas.year, fechas.month)],
    "Dia": fechas.day,
    "DiaSemanaNumero": fechas.day_of_week + 1,
    "DiaSemanaNombre": [DIAS[d] for d in fechas.day_of_week],
    "TipoDia": np.where(fechas.day_of_week >= 5, "Fin de semana", "Dia habil"),
    "Estacion": [estacion(m) for m in fechas.month],
    "Contexto": [contexto(d) for d in fechas],
})

def franja(hh):
    if hh < 0: return SD
    if hh <= 5: return "1. Madrugada (00-05)"
    if hh <= 11: return "2. Manana (06-11)"
    if hh <= 17: return "3. Tarde (12-17)"
    return "4. Noche (18-23)"
dim_hora = pd.DataFrame({"HoraKey": list(range(-1, 24))})
dim_hora["Hora"] = dim_hora["HoraKey"].map(lambda x: SD if x < 0 else f"{x:02d}:00 - {x:02d}:59")
dim_hora["FranjaHoraria"] = dim_hora["HoraKey"].map(franja)
dim_hora["HoraPico"] = dim_hora["HoraKey"].map(lambda x: SD if x < 0 else ("Hora pico" if x in (7, 8, 9, 17, 18, 19) else "Fuera de hora pico"))
dim_hora["Luz"] = dim_hora["HoraKey"].map(lambda x: SD if x < 0 else ("Diurno (07-19)" if 7 <= x <= 19 else "Nocturno (20-06)"))

BARRIOS = {
    1: "Retiro, San Nicolas, Puerto Madero, San Telmo, Monserrat, Constitucion",
    2: "Recoleta", 3: "Balvanera, San Cristobal",
    4: "La Boca, Barracas, Parque Patricios, Nueva Pompeya", 5: "Almagro, Boedo", 6: "Caballito",
    7: "Flores, Parque Chacabuco", 8: "Villa Soldati, Villa Riachuelo, Villa Lugano",
    9: "Liniers, Mataderos, Parque Avellaneda",
    10: "Villa Real, Monte Castro, Versalles, Floresta, Velez Sarsfield, Villa Luro",
    11: "Villa General Mitre, Villa Devoto, Villa del Parque, Villa Santa Rita",
    12: "Coghlan, Saavedra, Villa Urquiza, Villa Pueyrredon", 13: "Nunez, Belgrano, Colegiales", 14: "Palermo",
    15: "Chacarita, Villa Crespo, La Paternal, Villa Ortuzar, Agronomia, Parque Chas",
}
ZONA = {1: "Centro", 3: "Centro", 5: "Centro", 6: "Centro", 2: "Norte", 12: "Norte", 13: "Norte", 14: "Norte",
        4: "Sur", 7: "Sur", 8: "Sur", 9: "Sur", 10: "Oeste", 11: "Oeste", 15: "Oeste"}
dim_comuna = pd.DataFrame({"ComunaKey": list(range(0, 16))})
dim_comuna["Comuna"] = dim_comuna["ComunaKey"].map(lambda c: SD if c == 0 else f"Comuna {c:02d}")
dim_comuna["Zona"] = dim_comuna["ComunaKey"].map(ZONA).fillna(SD)
dim_comuna["Barrios"] = dim_comuna["ComunaKey"].map(BARRIOS).fillna(SD)

dim_tipovia = pd.DataFrame([(0, SD, SD), (1, "AVENIDA", "Via urbana"), (2, "CALLE", "Via urbana"),
                            (3, "AV. GRAL. PAZ", "Via rapida"), (4, "AUTOPISTA", "Via rapida")],
                           columns=["TipoViaKey", "TipoVia", "CategoriaVia"])
dim_vehiculo = pd.DataFrame(VEHICULOS, columns=["VehiculoKey", "Vehiculo", "CategoriaVehiculo"])
dim_gravedad = pd.DataFrame([(1, "LEVE", "No grave"), (2, "GRAVE", "Grave o mortal"), (3, "MORTAL", "Grave o mortal")],
                            columns=["GravedadKey", "Gravedad", "GrupoGravedad"])
dim_sexo = pd.DataFrame([(0, SD), (1, "Masculino"), (2, "Femenino")], columns=["SexoKey", "Sexo"])
dim_rango = pd.DataFrame([(0, SD), (1, "00-14"), (2, "15-24"), (3, "25-34"), (4, "35-44"), (5, "45-54"), (6, "55-64"), (7, "65 y mas")],
                         columns=["RangoEtarioKey", "RangoEtario"])
dim_rol = pd.DataFrame([(0, SD), (1, "PEATON"), (2, "CICLISTA"), (3, "CONDUCTOR"), (4, "PASAJERO")], columns=["RolKey", "Rol"])

tablas = {
    "DimTiempo": dim_tiempo, "DimHora": dim_hora, "DimComuna": dim_comuna, "DimTipoVia": dim_tipovia,
    "DimVehiculo": dim_vehiculo, "DimGravedad": dim_gravedad, "DimSexo": dim_sexo,
    "DimRangoEtario": dim_rango, "DimRolVictima": dim_rol,
    "FactSiniestro": fact_sin, "FactVictima": fact_vic,
}
for n, df in tablas.items():
    df.to_csv(os.path.join(OUT, f"{n}.csv"), index=False, encoding="utf-8")
    log[f"filas_{n}"] = len(df)

# integridad referencial
for fk, dim, k in [("FechaKey", dim_tiempo, "FechaKey"), ("HoraKey", dim_hora, "HoraKey"), ("ComunaKey", dim_comuna, "ComunaKey"),
                   ("TipoViaKey", dim_tipovia, "TipoViaKey"), ("VehiculoVictimaKey", dim_vehiculo, "VehiculoKey"),
                   ("ContraparteKey", dim_vehiculo, "VehiculoKey"), ("GravedadKey", dim_gravedad, "GravedadKey")]:
    assert fact_sin[fk].isin(dim[k]).all(), fk
for fk, dim, k in [("VehiculoKey", dim_vehiculo, "VehiculoKey"), ("SexoKey", dim_sexo, "SexoKey"),
                   ("RangoEtarioKey", dim_rango, "RangoEtarioKey"), ("RolKey", dim_rol, "RolKey")]:
    assert fact_vic[fk].isin(dim[k]).all(), fk

with open(os.path.join(OUT, "log_calidad_etl.json"), "w", encoding="utf-8") as f:
    json.dump(log, f, indent=2, ensure_ascii=False)
print(json.dumps(log, indent=2, ensure_ascii=False))
