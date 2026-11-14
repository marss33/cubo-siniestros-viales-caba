/* =====================================================================
   Data Warehouse: SiniestrosVialesDW  (SQL Server 2022/2025)
   Modelo estrella - Siniestros viales de la Ciudad de Buenos Aires 2019-2025
   Fuente: data.buenosaires.gob.ar - "Siniestros viales" (GCBA)
   ===================================================================== */
IF DB_ID('SiniestrosVialesDW') IS NULL
    CREATE DATABASE SiniestrosVialesDW;
GO
USE SiniestrosVialesDW;
GO
IF OBJECT_ID('dbo.FactVictima') IS NOT NULL DROP TABLE dbo.FactVictima;
IF OBJECT_ID('dbo.FactSiniestro') IS NOT NULL DROP TABLE dbo.FactSiniestro;
IF OBJECT_ID('dbo.DimTiempo') IS NOT NULL DROP TABLE dbo.DimTiempo;
IF OBJECT_ID('dbo.DimHora') IS NOT NULL DROP TABLE dbo.DimHora;
IF OBJECT_ID('dbo.DimComuna') IS NOT NULL DROP TABLE dbo.DimComuna;
IF OBJECT_ID('dbo.DimTipoVia') IS NOT NULL DROP TABLE dbo.DimTipoVia;
IF OBJECT_ID('dbo.DimVehiculo') IS NOT NULL DROP TABLE dbo.DimVehiculo;
IF OBJECT_ID('dbo.DimGravedad') IS NOT NULL DROP TABLE dbo.DimGravedad;
IF OBJECT_ID('dbo.DimSexo') IS NOT NULL DROP TABLE dbo.DimSexo;
IF OBJECT_ID('dbo.DimRangoEtario') IS NOT NULL DROP TABLE dbo.DimRangoEtario;
IF OBJECT_ID('dbo.DimRolVictima') IS NOT NULL DROP TABLE dbo.DimRolVictima;
GO

/* ------------------------- DIMENSIONES ------------------------- */
CREATE TABLE dbo.DimTiempo (
    FechaKey        INT          NOT NULL PRIMARY KEY,   -- AAAAMMDD
    Fecha           DATE         NOT NULL,
    Anio            SMALLINT     NOT NULL,
    Semestre        TINYINT      NOT NULL,
    SemestreNombre  NVARCHAR(10) NOT NULL,
    Trimestre       TINYINT      NOT NULL,
    TrimestreNombre NVARCHAR(10) NOT NULL,
    MesNumero       TINYINT      NOT NULL,
    MesNombre       NVARCHAR(12) NOT NULL,
    AnioMes         CHAR(7)      NOT NULL,              -- 2019-01
    AnioMesNombre   NVARCHAR(20) NOT NULL,
    Dia             TINYINT      NOT NULL,
    DiaSemanaNumero TINYINT      NOT NULL,
    DiaSemanaNombre NVARCHAR(10) NOT NULL,
    TipoDia         NVARCHAR(15) NOT NULL,              -- Dia habil / Fin de semana
    Estacion        NVARCHAR(10) NOT NULL,
    Contexto        NVARCHAR(25) NOT NULL               -- Pre-pandemia / ASPO / Post-ASPO
);
CREATE TABLE dbo.DimHora (
    HoraKey       SMALLINT     NOT NULL PRIMARY KEY,    -- -1 = sin dato
    Hora          NVARCHAR(15) NOT NULL,
    FranjaHoraria NVARCHAR(25) NOT NULL,
    HoraPico      NVARCHAR(20) NOT NULL,
    Luz           NVARCHAR(20) NOT NULL
);
CREATE TABLE dbo.DimComuna (
    ComunaKey TINYINT       NOT NULL PRIMARY KEY,       -- 0 = sin dato
    Comuna    NVARCHAR(12)  NOT NULL,
    Zona      NVARCHAR(10)  NOT NULL,
    Barrios   NVARCHAR(120) NOT NULL
);
CREATE TABLE dbo.DimTipoVia (
    TipoViaKey   TINYINT      NOT NULL PRIMARY KEY,
    TipoVia      NVARCHAR(20) NOT NULL,
    CategoriaVia NVARCHAR(15) NOT NULL
);
CREATE TABLE dbo.DimVehiculo (            -- dimension de rol multiple: victima y contraparte
    VehiculoKey       TINYINT      NOT NULL PRIMARY KEY,
    Vehiculo          NVARCHAR(25) NOT NULL,
    CategoriaVehiculo NVARCHAR(25) NOT NULL
);
CREATE TABLE dbo.DimGravedad (
    GravedadKey   TINYINT      NOT NULL PRIMARY KEY,
    Gravedad      NVARCHAR(10) NOT NULL,
    GrupoGravedad NVARCHAR(20) NOT NULL
);
CREATE TABLE dbo.DimSexo        (SexoKey TINYINT NOT NULL PRIMARY KEY, Sexo NVARCHAR(10) NOT NULL);
CREATE TABLE dbo.DimRangoEtario (RangoEtarioKey TINYINT NOT NULL PRIMARY KEY, RangoEtario NVARCHAR(10) NOT NULL);
CREATE TABLE dbo.DimRolVictima  (RolKey TINYINT NOT NULL PRIMARY KEY, Rol NVARCHAR(12) NOT NULL);
GO

/* ------------------------- TABLAS DE HECHOS ------------------------- */
-- Grano: 1 fila = 1 siniestro vial
CREATE TABLE dbo.FactSiniestro (
    SiniestroID        VARCHAR(20)  NOT NULL PRIMARY KEY,
    FechaKey           INT          NOT NULL REFERENCES dbo.DimTiempo(FechaKey),
    HoraKey            SMALLINT     NOT NULL REFERENCES dbo.DimHora(HoraKey),
    ComunaKey          TINYINT      NOT NULL REFERENCES dbo.DimComuna(ComunaKey),
    TipoViaKey         TINYINT      NOT NULL REFERENCES dbo.DimTipoVia(TipoViaKey),
    VehiculoVictimaKey TINYINT      NOT NULL REFERENCES dbo.DimVehiculo(VehiculoKey),
    ContraparteKey     TINYINT      NOT NULL REFERENCES dbo.DimVehiculo(VehiculoKey),
    GravedadKey        TINYINT      NOT NULL REFERENCES dbo.DimGravedad(GravedadKey),
    CantSiniestros     INT          NOT NULL,     -- medida aditiva (=1)
    TotalVictimas      INT          NOT NULL,
    VictimasLeves      INT          NOT NULL,
    VictimasGraves     INT          NOT NULL,
    VictimasMortales   INT          NOT NULL,
    Latitud            DECIMAL(9,6) NULL,         -- atributos degenerados
    Longitud           DECIMAL(9,6) NULL,
    Direccion          NVARCHAR(200) NULL,
    Participantes      NVARCHAR(60) NULL
);
-- Grano: 1 fila = 1 victima
CREATE TABLE dbo.FactVictima (
    VictimaID      INT         NOT NULL PRIMARY KEY,
    SiniestroID    VARCHAR(20) NOT NULL REFERENCES dbo.FactSiniestro(SiniestroID),
    FechaKey       INT         NOT NULL REFERENCES dbo.DimTiempo(FechaKey),
    HoraKey        SMALLINT    NOT NULL REFERENCES dbo.DimHora(HoraKey),
    ComunaKey      TINYINT     NOT NULL REFERENCES dbo.DimComuna(ComunaKey),
    TipoViaKey     TINYINT     NOT NULL REFERENCES dbo.DimTipoVia(TipoViaKey),
    VehiculoKey    TINYINT     NOT NULL REFERENCES dbo.DimVehiculo(VehiculoKey),
    ContraparteKey TINYINT     NOT NULL REFERENCES dbo.DimVehiculo(VehiculoKey),
    SexoKey        TINYINT     NOT NULL REFERENCES dbo.DimSexo(SexoKey),
    RangoEtarioKey TINYINT     NOT NULL REFERENCES dbo.DimRangoEtario(RangoEtarioKey),
    RolKey         TINYINT     NOT NULL REFERENCES dbo.DimRolVictima(RolKey),
    GravedadKey    TINYINT     NOT NULL REFERENCES dbo.DimGravedad(GravedadKey),
    Edad           TINYINT     NULL,
    CantVictimas   INT         NOT NULL,          -- =1
    CantFallecidos INT         NOT NULL           -- 1 si fallecio
);
GO
CREATE INDEX IX_FactSiniestro_Fecha  ON dbo.FactSiniestro(FechaKey);
CREATE INDEX IX_FactSiniestro_Comuna ON dbo.FactSiniestro(ComunaKey);
CREATE INDEX IX_FactVictima_Fecha    ON dbo.FactVictima(FechaKey);
GO

/* ------------------------- VISTAS ------------------------- */
-- Vista minable mensual (para regresion / numero indice base 100)
CREATE OR ALTER VIEW dbo.vw_SerieMensualIndice AS
WITH m AS (
    SELECT t.AnioMes, SUM(f.CantSiniestros) AS Siniestros, SUM(f.VictimasMortales) AS Mortales
    FROM dbo.FactSiniestro f JOIN dbo.DimTiempo t ON t.FechaKey = f.FechaKey
    GROUP BY t.AnioMes
)
SELECT AnioMes, Siniestros, Mortales,
       SUM(Siniestros) OVER (ORDER BY AnioMes ROWS UNBOUNDED PRECEDING)                         AS Acumulado,
       CAST(Siniestros * 100.0 / FIRST_VALUE(Siniestros) OVER (ORDER BY AnioMes) AS DECIMAL(9,2)) AS IndiceBase100,
       CAST(SUM(Siniestros) OVER (ORDER BY AnioMes ROWS UNBOUNDED PRECEDING) * 100.0
            / FIRST_VALUE(Siniestros) OVER (ORDER BY AnioMes) AS DECIMAL(12,2))                 AS IndiceAcumulado
FROM m;
GO
-- Vista desnormalizada usada por Excel / Google Sheets
CREATE OR ALTER VIEW dbo.vw_SiniestrosDetalle AS
SELECT f.SiniestroID, t.Fecha, t.Anio, t.Trimestre, t.MesNumero, t.MesNombre, t.AnioMes, t.DiaSemanaNombre, t.TipoDia,
       t.Estacion, t.Contexto, h.HoraKey AS Hora, h.FranjaHoraria, h.HoraPico, c.Comuna, c.Zona, v.TipoVia, v.CategoriaVia,
       vv.Vehiculo AS VehiculoVictima, vv.CategoriaVehiculo AS CategoriaVictima, vc.Vehiculo AS Contraparte,
       g.Gravedad, f.CantSiniestros, f.TotalVictimas, f.VictimasLeves, f.VictimasGraves, f.VictimasMortales
FROM dbo.FactSiniestro f
JOIN dbo.DimTiempo t    ON t.FechaKey = f.FechaKey
JOIN dbo.DimHora h      ON h.HoraKey = f.HoraKey
JOIN dbo.DimComuna c    ON c.ComunaKey = f.ComunaKey
JOIN dbo.DimTipoVia v   ON v.TipoViaKey = f.TipoViaKey
JOIN dbo.DimVehiculo vv ON vv.VehiculoKey = f.VehiculoVictimaKey
JOIN dbo.DimVehiculo vc ON vc.VehiculoKey = f.ContraparteKey
JOIN dbo.DimGravedad g  ON g.GravedadKey = f.GravedadKey;
GO
