# Cubo OLAP y Minería de Datos — Siniestros Viales CABA (2019-2025)

Data Warehouse, cubo multidimensional en **SQL Server Analysis Services** construido con **C# en Visual Studio 2026**,
número índice base 100 y **minería de datos** (10 modelos SSAS + técnicas complementarias en Python) sobre los
siniestros viales de la Ciudad Autónoma de Buenos Aires.

> Trabajo práctico de la materia Base de Datos Aplicada.

## Datos

Fuente: [Portal de Datos Abiertos del GCBA — Siniestros viales](https://data.buenosaires.gob.ar/dataset/victimas-siniestros-viales)
(Secretaría de Transporte, Observatorio de Movilidad y Seguridad Vial), licencia Creative Commons Atribución.

| Archivo | Contenido |
|---|---|
| `datos_originales/siniestros_viales_hechos.csv` | 65.818 siniestros (1 fila = 1 siniestro) |
| `datos_originales/siniestros_viales_victimas.csv` | 75.197 víctimas (1 fila = 1 víctima) |
| `datos_originales/descargar_datos.ps1` | Vuelve a descargar los archivos desde el portal |

## Arquitectura

```
CSV GCBA ──ETL (Python)──► SiniestrosVialesDW (SQL Server, modelo estrella / constelación)
                                   │
                                   ├──► Cubo "Siniestros Viales" (SSAS 2019, MOLAP)  ◄── programa C# (AMO)
                                   ├──► 5 estructuras / 10 modelos de minería (SSAS)  ◄── programa C# (AMO)
                                   ├──► Consultas MDX y DMX                           ◄── programa C# (ADOMD.NET)
                                   └──► Excel (tablas dinámicas OLAP) y Google Sheets
```

* **Tablas de hechos:** `FactSiniestro` (grano: 1 siniestro) y `FactVictima` (grano: 1 víctima).
* **Dimensiones:** Tiempo, Hora, Comuna, Tipo de vía, Vehículo (rol múltiple: víctima y contraparte), Gravedad, Sexo, Rango etario, Rol.
* Diagrama: [`graficos/00_modelo_estrella.png`](graficos/00_modelo_estrella.png) — DER de origen: [`graficos/00_der_origen.png`](graficos/00_der_origen.png).

## Requisitos

* Windows con **SQL Server** (motor relacional; probado con SQL Server 2025) para el Data Warehouse.
* **SQL Server 2019 Analysis Services** en modo Multidimensional (instancia `localhost\SSAS2019`). Se usa 2019 porque
  SSAS 2022/2025 discontinuaron el Data Mining. `ssas/instalar_ssas2019.ps1` instala solo Analysis Services.
* **Visual Studio 2026** (o 2022) con desarrollo de escritorio .NET y la extensión *Microsoft Analysis Services Projects*.
* **Python 3.12** con `pip install -r scripts/requirements.txt` (y `scikit-learn statsmodels mlxtend matplotlib openpyxl` para la minería en Python y el Excel).
* ODBC Driver 18 for SQL Server.

## Cómo ejecutarlo

1. Iniciar los servicios (PowerShell como administrador): `Start-Service MSSQLSERVER, 'MSOLAP$SSAS2019'`
2. ETL y carga del DW:
   ```
   python scripts/01_etl.py
   python scripts/03_cargar_dw.py
   ```
   Crea `SiniestrosVialesDW`, carga las tablas y las vistas minables (`sql/02_vistas_minables.sql`).
   Darle lectura a la cuenta de servicio de SSAS: `NT SERVICE\MSOLAP$SSAS2019` → rol `db_datareader` en `SiniestrosVialesDW`.
3. Abrir `visual_studio/CuboSiniestrosViales.sln`, dejar **CuboSiniestrosViales.CSharp** como proyecto de inicio y presionar **F5**.
   Menú: `1` todo (cubo + minería + consultas, ~5-12 min) · `2` solo consultas · `3` solo cubo · `4` solo minería.
4. Excel: `excel/TP_Siniestros_Viales_CABA.xlsx` → Datos → Actualizar todo.

El proyecto **CuboSiniestrosViales** (Analysis Services) muestra el cubo en los diseñadores de Visual Studio
(pestaña *Estructura de cubo* = diagrama de hechos y dimensiones). Al implementarlo se despliega en la base
`SiniestrosVialesOLAP_Diseno`, separada, porque implementar reemplaza la base completa y borraría la minería.

## Contenido del repositorio (guía para documentar)

| Carpeta / archivo | Qué contiene | Para documentar |
|---|---|---|
| `sql/01_crear_dw.sql` | Tablas, claves, índices y vistas del DW (incluye `vw_SerieMensualIndice`) | Diseño del DW, tabla de hechos y dimensiones |
| `sql/02_vistas_minables.sql` | Vistas minables (`vmin_*`) armadas desde la estrella | Vista minable de cada algoritmo |
| `datos_limpios/` + `log_calidad_etl.json` | Tablas del modelo estrella y conteo de problemas corregidos | Proceso ETL y calidad de datos |
| `visual_studio/CuboSiniestrosViales.CSharp/` | `ConstructorCubo.cs`, `ConstructorMineria.cs`, `ConsultasMdx.cs`, `ConsultasDmx.cs` | Construcción del cubo, jerarquías, medidas MDX, modelos de minería |
| `visual_studio/CuboSiniestrosViales/` | Proyecto Analysis Services (dimensiones, DSV, cubo) | Capturas de los diseñadores |
| `ssas/resultado_programa_csharp.txt` | Salida completa del programa (MDX + DMX) | Validación del cubo, índice base 100, resultados de minería |
| `ssas/resultado_consultas_dmx.txt`, `mineria/resultados_ssas.json`, `mineria/evaluacion_ssas.json`, `mineria/predicciones_ssas_*.csv` | Resultados y evaluación (AUC, lift) de los modelos SSAS | Minería en SSAS |
| `mineria/*.csv`, `mineria/resultados.json` | Resultados de la minería en Python (regresión, clasificación, clustering, DBSCAN, Apriori, anomalías, correlación) | Minería complementaria |
| `graficos/` | 33 gráficos (PNG) | Figuras del informe |
| `excel/` | Libro Excel (índice base 100 con fórmulas, pivots OLAP) y CSV para Google Sheets | Demostración Excel / Google Sheets |
| `scripts/` | ETL, minería Python, evaluación SSAS, Excel, diagramas y generador del proyecto VS | Reproducibilidad |

### Algoritmos de minería

| Estructura SSAS | Modelos (algoritmo de Microsoft) |
|---|---|
| MS Gravedad Siniestros (30% prueba) | Decision Trees, Naive Bayes, Logistic Regression, Neural Network, Clustering |
| MS Asociacion Siniestros | Association Rules |
| MS Serie Mensual | Time Series (ARTXP + ARIMA) |
| MS Victima Fatal (30% prueba) | Decision Trees, Naive Bayes |
| MS Perfil Comunas | Clustering |

Complemento en Python: Random Forest, K-Means, jerárquico (Ward), DBSCAN geoespacial, Apriori, Holt-Winters,
detección de anomalías (z-score / Isolation Forest) y correlación (Pearson / Spearman).
