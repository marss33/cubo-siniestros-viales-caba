<#
  descargar_datos.ps1 - Descarga los datos abiertos "Siniestros viales" del Gobierno de la Ciudad de Buenos Aires
  (https://data.buenosaires.gob.ar/dataset/victimas-siniestros-viales) a esta carpeta.
  Uso: powershell -ExecutionPolicy Bypass -File datos_originales\descargar_datos.ps1
#>
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$base = "https://data.buenosaires.gob.ar/dataset/victimas-siniestros-viales/resource"
$archivos = [ordered]@{
  "siniestros_viales_hechos.csv"      = "$base/40ec993a-00ad-40e5-936f-0a25f8d2c90b/download"
  "siniestros_viales_victimas.csv"    = "$base/41beafc0-ca1c-430d-a29d-07c425d0aa20/download"
  "metodologia_siniestros_viales.pdf" = "$base/42ba7530-b956-4082-8ac8-4dfba2fbb360/download"
}
foreach ($n in $archivos.Keys) {
  Write-Host "Descargando $n ..."
  Invoke-WebRequest $archivos[$n] -OutFile (Join-Path $PSScriptRoot $n) -UseBasicParsing
}
Get-ChildItem $PSScriptRoot -File | Where-Object { $_.Extension -ne ".ps1" } | Select-Object Name, Length
