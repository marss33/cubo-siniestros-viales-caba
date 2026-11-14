"""05_diagramas.py - Diagramas del modelo de origen (DER) y del Data Warehouse (estrella/constelacion)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from estilo import *
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = sys.argv[1]
G = os.path.join(ROOT, "graficos")

def caja(ax, x, y, w, titulo, campos, color, pk=None):
    h = 0.42 + 0.30 * len(campos)
    ax.add_patch(FancyBboxPatch((x, y - h), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=SURFACE, ec=color, lw=1.6, zorder=2))
    ax.add_patch(FancyBboxPatch((x, y - 0.42), w, 0.42, boxstyle="round,pad=0.02,rounding_size=0.08", fc=color, ec=color, lw=1.6, zorder=3))
    ax.text(x + w / 2, y - 0.21, titulo, ha="center", va="center", color="white", fontsize=9.5, fontweight="bold", zorder=4)
    for i, c in enumerate(campos):
        ax.text(x + 0.12, y - 0.62 - 0.30 * i, c, ha="left", va="center", fontsize=7.6, color=INK, zorder=4,
                fontweight="bold" if (pk and c.startswith(pk)) or c.startswith("PK") else "normal")
    return (x, y, w, h)

def linea(ax, p1, p2, color=MUTED):
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=color, lw=1.2, zorder=1)

# ---------------------------------------------------------------- Modelo estrella / constelacion
fig, ax = plt.subplots(figsize=(15, 10.5)); ax.set_xlim(0, 30); ax.set_ylim(0, 21); ax.axis("off")
DIM, FAC = AZUL, NARANJA
fs = caja(ax, 8.6, 14.2, 5.0, "FactSiniestro", ["PK SiniestroID", "FK FechaKey", "FK HoraKey", "FK ComunaKey", "FK TipoViaKey", "FK VehiculoVictimaKey",
                                                 "FK ContraparteKey", "FK GravedadKey", "CantSiniestros", "TotalVictimas", "VictimasLeves",
                                                 "VictimasGraves", "VictimasMortales", "Latitud / Longitud / Direccion"], FAC)
fv = caja(ax, 16.6, 14.2, 5.0, "FactVictima", ["PK VictimaID", "FK SiniestroID", "FK FechaKey", "FK HoraKey", "FK ComunaKey", "FK TipoViaKey",
                                               "FK VehiculoKey", "FK ContraparteKey", "FK SexoKey", "FK RangoEtarioKey", "FK RolKey", "FK GravedadKey",
                                               "Edad", "CantVictimas", "CantFallecidos"], FAC)
dims = {
    "DimTiempo": ((0.4, 20.6), ["PK FechaKey", "Fecha", "Anio / Semestre", "Trimestre / Mes", "AnioMes", "DiaSemana / TipoDia", "Estacion", "Contexto (pandemia)"]),
    "DimHora": ((0.4, 11.6), ["PK HoraKey", "Hora", "FranjaHoraria", "HoraPico", "Luz"]),
    "DimComuna": ((0.4, 6.4), ["PK ComunaKey", "Comuna", "Zona", "Barrios"]),
    "DimTipoVia": ((9.6, 3.0), ["PK TipoViaKey", "TipoVia", "CategoriaVia"]),
    "DimGravedad": ((14.4, 3.0), ["PK GravedadKey", "Gravedad", "GrupoGravedad"]),
    "DimVehiculo": ((13.4, 20.6), ["PK VehiculoKey", "Vehiculo", "CategoriaVehiculo", "(rol: Victima y Contraparte)"]),
    "DimSexo": ((24.4, 20.6), ["PK SexoKey", "Sexo"]),
    "DimRangoEtario": ((24.4, 16.6), ["PK RangoEtarioKey", "RangoEtario"]),
    "DimRolVictima": ((24.4, 12.6), ["PK RolKey", "Rol"]),
}
B = {}
for n, ((x, y), campos) in dims.items():
    B[n] = caja(ax, x, y, 4.6, n, campos, DIM)
def centro(b): x, y, w, h = b; return (x + w / 2, y - h / 2)
for n in ["DimTiempo", "DimHora", "DimComuna", "DimTipoVia", "DimGravedad", "DimVehiculo"]:
    linea(ax, centro(B[n]), centro(fs)); linea(ax, centro(B[n]), centro(fv))
for n in ["DimSexo", "DimRangoEtario", "DimRolVictima"]:
    linea(ax, centro(B[n]), centro(fv))
linea(ax, centro(fs), centro(fv), color=FAC)
ax.text(15.1, 9.3, "1 : N", color=FAC, fontsize=9, ha="center")
ax.text(0.4, 0.6, "Esquema de constelación (2 tablas de hechos con dimensiones conformadas). Naranja = hechos, azul = dimensiones.", fontsize=9, color=INK2)
ax.set_title("Data Warehouse SiniestrosVialesDW - modelo dimensional", loc="left")
fig.savefig(os.path.join(G, "00_modelo_estrella.png"), dpi=160, bbox_inches="tight"); plt.close(fig)

# ---------------------------------------------------------------- DER de origen
fig, ax = plt.subplots(figsize=(13, 6.4)); ax.set_xlim(0, 26); ax.set_ylim(0, 13); ax.axis("off")
h = caja(ax, 0.5, 12.5, 8.6, "siniestros_viales_hechos.csv (65.818 filas)",
         ["PK id_siniestro", "numero_total_de_victimas / leve / grave / mortal", "fecha_siniestro, anio, mes, dia", "hora_siniestro, rango_horario",
          "direccion_normalizada_siniestro", "comuna_siniestro", "tipo_de_via_siniestro", "geocodificacion_plana, longitud, latitud",
          "participantes_siniestro", "modo_desplazamiento_victima", "contraparte_siniestro", "gravedad_siniestro"], MUTED)
v = caja(ax, 16.5, 12.5, 8.6, "siniestros_viales_victimas.csv (75.197 filas)",
         ["FK id_siniestro", "fecha_siniestro, anio_siniestro", "modo_desplazamiento_victima", "sexo_victima", "edad_victima",
          "gravedad_victima", "rol_victima", "fecha_fallecimiento_victima"], MUTED)
linea(ax, (9.1, 9.0), (16.5, 9.0), color=INK2)
ax.text(9.4, 9.25, "1", fontsize=11, color=INK); ax.text(16.0, 9.25, "N", fontsize=11, color=INK)
ax.text(12.8, 8.4, "un siniestro tiene\nuna o más víctimas", ha="center", fontsize=9, color=INK2)
ax.set_title("Modelo de origen (OLTP / archivos abiertos GCBA)", loc="left")
fig.savefig(os.path.join(G, "00_der_origen.png"), dpi=160, bbox_inches="tight"); plt.close(fig)
print("diagramas ok")
