/* =====================================================================
   Vistas minables para SSAS Data Mining (Visual Studio)
   Cada algoritmo necesita los datos con una forma distinta: se arman
   desde el modelo estrella (FactSiniestro / FactVictima + dimensiones).
   ===================================================================== */
USE SiniestrosVialesDW;
GO

/* 1) Clasificacion / clustering / asociacion: 1 fila = 1 siniestro con datos completos
      (se excluyen los registros "SIN DATO" por el sesgo de carga detectado) */
CREATE OR ALTER VIEW dbo.vmin_Siniestros AS
SELECT f.SiniestroID,
       h.HoraKey            AS Hora,
       h.FranjaHoraria,
       t.TipoDia,
       t.DiaSemanaNombre    AS DiaSemana,
       t.Estacion,
       t.Contexto,
       c.Comuna,
       c.Zona,
       v.TipoVia,
       vv.Vehiculo          AS VehiculoVictima,
       vc.Vehiculo          AS Contraparte,
       f.TotalVictimas,
       CASE WHEN f.GravedadKey >= 2 THEN 'GRAVE O MORTAL' ELSE 'LEVE' END AS Gravedad
FROM dbo.FactSiniestro f
JOIN dbo.DimTiempo   t  ON t.FechaKey   = f.FechaKey
JOIN dbo.DimHora     h  ON h.HoraKey    = f.HoraKey
JOIN dbo.DimComuna   c  ON c.ComunaKey  = f.ComunaKey
JOIN dbo.DimTipoVia  v  ON v.TipoViaKey = f.TipoViaKey
JOIN dbo.DimVehiculo vv ON vv.VehiculoKey = f.VehiculoVictimaKey
JOIN dbo.DimVehiculo vc ON vc.VehiculoKey = f.ContraparteKey
WHERE f.ComunaKey > 0 AND f.TipoViaKey > 0 AND f.VehiculoVictimaKey > 0
  AND f.ContraparteKey > 0 AND f.HoraKey >= 0;
GO

/* 2) Perfil de victima fatal: 1 fila = 1 victima con sexo, edad, vehiculo y via informados */
CREATE OR ALTER VIEW dbo.vmin_Victimas AS
SELECT fv.VictimaID,
       CAST(fv.Edad AS INT) AS Edad,
       r.RangoEtario,
       s.Sexo,
       ve.Vehiculo,
       v.TipoVia,
       h.HoraKey            AS Hora,
       h.FranjaHoraria,
       t.TipoDia,
       c.Zona,
       CASE WHEN fv.CantFallecidos = 1 THEN 'FALLECIO' ELSE 'SOBREVIVIO' END AS Desenlace
FROM dbo.FactVictima fv
JOIN dbo.DimTiempo      t ON t.FechaKey = fv.FechaKey
JOIN dbo.DimHora        h ON h.HoraKey  = fv.HoraKey
JOIN dbo.DimComuna      c ON c.ComunaKey = fv.ComunaKey
JOIN dbo.DimTipoVia     v ON v.TipoViaKey = fv.TipoViaKey
JOIN dbo.DimVehiculo   ve ON ve.VehiculoKey = fv.VehiculoKey
JOIN dbo.DimSexo        s ON s.SexoKey = fv.SexoKey
JOIN dbo.DimRangoEtario r ON r.RangoEtarioKey = fv.RangoEtarioKey
WHERE fv.SexoKey > 0 AND fv.Edad IS NOT NULL AND fv.TipoViaKey > 0
  AND fv.VehiculoKey > 0 AND fv.HoraKey >= 0;
GO

/* 3) Serie de tiempo: vector tiempo (mes) + vector dato (siniestros, mortales) */
CREATE OR ALTER VIEW dbo.vmin_SerieMensual AS
SELECT DATEFROMPARTS(t.Anio, t.MesNumero, 1)  AS Mes,
       CAST(SUM(f.CantSiniestros)   AS FLOAT)  AS Siniestros,
       CAST(SUM(f.VictimasMortales) AS FLOAT)  AS Mortales,
       CAST(SUM(f.TotalVictimas)    AS FLOAT)  AS Victimas
FROM dbo.FactSiniestro f
JOIN dbo.DimTiempo t ON t.FechaKey = f.FechaKey
GROUP BY t.Anio, t.MesNumero;
GO

/* 4) Perfil de comunas para clustering: 1 fila = 1 comuna */
CREATE OR ALTER VIEW dbo.vmin_PerfilComunas AS
SELECT c.Comuna,
       c.Zona,
       CAST(COUNT(*) * 1.0 / COUNT(DISTINCT t.Anio) AS FLOAT)                                                AS SiniestrosAnuales,
       CAST(100.0 * SUM(CASE WHEN vv.Vehiculo = 'MOTO' THEN 1 ELSE 0 END) / COUNT(*) AS FLOAT)               AS PctMoto,
       CAST(100.0 * SUM(CASE WHEN vv.Vehiculo = 'PEATON' THEN 1 ELSE 0 END) / COUNT(*) AS FLOAT)             AS PctPeaton,
       CAST(100.0 * SUM(CASE WHEN vv.Vehiculo = 'BICICLETA' THEN 1 ELSE 0 END) / COUNT(*) AS FLOAT)          AS PctBicicleta,
       CAST(100.0 * SUM(CASE WHEN h.Luz = 'Nocturno (20-06)' THEN 1 ELSE 0 END) / COUNT(*) AS FLOAT)         AS PctNocturno,
       CAST(100.0 * SUM(CASE WHEN t.TipoDia = 'Fin de semana' THEN 1 ELSE 0 END) / COUNT(*) AS FLOAT)        AS PctFinDeSemana,
       CAST(100.0 * SUM(CASE WHEN v.CategoriaVia = 'Via rapida' THEN 1 ELSE 0 END) / COUNT(*) AS FLOAT)      AS PctViaRapida,
       CAST(100.0 * SUM(CASE WHEN vc.CategoriaVehiculo = 'Vehiculo pesado' THEN 1 ELSE 0 END) / COUNT(*) AS FLOAT) AS PctTransportePesado,
       CAST(100.0 * SUM(CASE WHEN f.GravedadKey >= 2 THEN 1 ELSE 0 END) / COUNT(*) AS FLOAT)                 AS PctGraveMortal
FROM dbo.FactSiniestro f
JOIN dbo.DimTiempo   t  ON t.FechaKey = f.FechaKey
JOIN dbo.DimHora     h  ON h.HoraKey = f.HoraKey
JOIN dbo.DimComuna   c  ON c.ComunaKey = f.ComunaKey
JOIN dbo.DimTipoVia  v  ON v.TipoViaKey = f.TipoViaKey
JOIN dbo.DimVehiculo vv ON vv.VehiculoKey = f.VehiculoVictimaKey
JOIN dbo.DimVehiculo vc ON vc.VehiculoKey = f.ContraparteKey
WHERE f.ComunaKey > 0
GROUP BY c.Comuna, c.Zona;
GO
