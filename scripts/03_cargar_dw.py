"""
03_cargar_dw.py - Crea el Data Warehouse SiniestrosVialesDW en SQL Server, carga las tablas del modelo
estrella (datos_limpios/) y crea las vistas minables para la mineria de datos.
Uso: python scripts/03_cargar_dw.py [carpeta_del_repo] [servidor_sql]   (por defecto: este repo, localhost)
"""
import sys, os, re
import pandas as pd
import pyodbc

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = sys.argv[2] if len(sys.argv) > 2 else "localhost"
D = os.path.join(ROOT, "datos_limpios")
CS = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SERVER};Trusted_Connection=yes;TrustServerCertificate=yes;"


def ejecutar_script(nombre):
    cn = pyodbc.connect(CS + "DATABASE=master;", autocommit=True)
    sql = open(os.path.join(ROOT, "sql", nombre), encoding="utf-8").read()
    for lote in re.split(r"^\s*GO\s*$", sql, flags=re.M | re.I):
        if lote.strip():
            cn.cursor().execute(lote)
    cn.close()
    print("Ejecutado", nombre)


ejecutar_script("01_crear_dw.sql")

cn = pyodbc.connect(CS + "DATABASE=SiniestrosVialesDW;")
cur = cn.cursor(); cur.fast_executemany = True
ORDEN = ["DimTiempo", "DimHora", "DimComuna", "DimTipoVia", "DimVehiculo", "DimGravedad", "DimSexo",
         "DimRangoEtario", "DimRolVictima", "FactSiniestro", "FactVictima"]
for t in ORDEN:
    df = pd.read_csv(os.path.join(D, t + ".csv"), encoding="utf-8", keep_default_na=False, na_values=[""])
    df = df.astype(object).where(pd.notna(df), None)
    cols = ",".join(f"[{c}]" for c in df.columns)
    q = f"INSERT INTO dbo.{t} ({cols}) VALUES ({','.join('?' * len(df.columns))})"
    filas = [tuple(r) for r in df.itertuples(index=False, name=None)]
    for i in range(0, len(filas), 20000):
        cur.executemany(q, filas[i:i + 20000])
    cn.commit()
    n = cur.execute(f"SELECT COUNT(*) FROM dbo.{t}").fetchone()[0]
    print(f"{t:16s} {n:>7,d} filas")
cn.close()

ejecutar_script("02_vistas_minables.sql")
print("Data Warehouse listo.")
