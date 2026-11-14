"""
07_proyecto_visual_studio.py - Convierte la definicion del cubo desplegado (ssas/SiniestrosVialesOLAP.xmla)
en un proyecto de Visual Studio "Analysis Services Multidimensional" (.sln + .dwproj + .ds/.dsv/.dim/.cube/
.partitions/.role/.database), compatible con Visual Studio 2022 y 2026 con la extension
"Microsoft Analysis Services Projects".
Uso: python 07_proyecto_visual_studio.py <carpeta_del_proyecto>
"""
import sys, os, re, uuid

ROOT = sys.argv[1]
SERVIDOR = sys.argv[2] if len(sys.argv) > 2 else "localhost\\SSAS2019"
XMLA = os.path.join(ROOT, "ssas", "SiniestrosVialesOLAP.xmla")
PROY = "CuboSiniestrosViales"
OUT = os.path.join(ROOT, "visual_studio", PROY)
os.makedirs(OUT, exist_ok=True)
txt = open(XMLA, encoding="utf-8-sig").read()

NS = ('xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
      'xmlns:ddl2="http://schemas.microsoft.com/analysisservices/2003/engine/2" xmlns:ddl2_2="http://schemas.microsoft.com/analysisservices/2003/engine/2/2" '
      'xmlns:ddl100_100="http://schemas.microsoft.com/analysisservices/2008/engine/100/100" xmlns:ddl200="http://schemas.microsoft.com/analysisservices/2010/engine/200" '
      'xmlns:ddl200_200="http://schemas.microsoft.com/analysisservices/2010/engine/200/200" xmlns:ddl300="http://schemas.microsoft.com/analysisservices/2011/engine/300" '
      'xmlns:ddl300_300="http://schemas.microsoft.com/analysisservices/2011/engine/300/300" xmlns:ddl400="http://schemas.microsoft.com/analysisservices/2012/engine/400" '
      'xmlns:ddl400_400="http://schemas.microsoft.com/analysisservices/2012/engine/400/400" xmlns:ddl500="http://schemas.microsoft.com/analysisservices/2013/engine/500" '
      'xmlns:ddl500_500="http://schemas.microsoft.com/analysisservices/2013/engine/500/500" xmlns:dwd="http://schemas.microsoft.com/DataWarehouse/Designer/1.0"')
DEF = 'xmlns="http://schemas.microsoft.com/analysisservices/2003/engine"'
def dtn(): return f'dwd:design-time-name="{uuid.uuid4()}"'

def bloques(tag, ind):
    """Devuelve los bloques <tag>...</tag> con la indentacion dada (objetos de primer nivel de la base)."""
    pat = re.compile(rf"^{' ' * ind}<{tag}(?: [^>]*)?>.*?^{' ' * ind}</{tag}>", re.S | re.M)
    return pat.findall(txt)

def desindentar(b, ind):
    return "\n".join(l[ind:] if l.startswith(" " * ind) else l for l in b.split("\n"))

def con_ns(b, tag):
    # agrega los namespaces al elemento raiz del archivo
    return re.sub(rf"^<{tag}(\s[^>]*)?>", lambda m: f"<{tag} {NS}{m.group(1) or ''} {dtn()} {DEF}>", b, count=1)

def guardar(nombre, contenido):
    with open(os.path.join(OUT, nombre), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(contenido.replace("\r\n", "\n"))
    return nombre

def id_de(b): return re.search(r"<ID>(.*?)</ID>", b).group(1)
def nombre_archivo(s): return re.sub(r'[\\/:*?"<>|]', "_", s)

items = {"ds": [], "dsv": [], "dim": [], "cube": [], "role": [], "dmm": []}

# ---- Data sources
for b in bloques("DataSource", 8):
    b = desindentar(b, 8)
    b = b.replace("<ImpersonationMode>ImpersonateServiceAccount</ImpersonationMode>",
                  "<ImpersonationMode>ImpersonateServiceAccount</ImpersonationMode>\n    <ImpersonationInfoSecurity>Unchanged</ImpersonationInfoSecurity>")
    b = b.replace("</ConnectionString>", "</ConnectionString>\n  <ConnectionStringSecurity>Unchanged</ConnectionStringSecurity>")
    DS_ID = id_de(b); DS_CONN = re.search(r"<ConnectionString>(.*?)</ConnectionString>", b).group(1)
    items["ds"].append(guardar(nombre_archivo(DS_ID) + ".ds", con_ns(b, "DataSource")))

# ---- Data source view
for b in bloques("DataSourceView", 8):
    b = desindentar(b, 8)
    items["dsv"].append(guardar(nombre_archivo(id_de(b)) + ".dsv", con_ns(b, "DataSourceView")))
    DSV_ID = id_de(b)

# ---- Dimensiones
for b in bloques("Dimension", 8):
    b = desindentar(b, 8)
    items["dim"].append(guardar(nombre_archivo(id_de(b)) + ".dim", con_ns(b, "Dimension")))

# ---- Cubo + particiones (las particiones van en un archivo .partitions aparte)
for b in bloques("Cube", 8):
    b = desindentar(b, 8)
    cubo_id = id_de(b)
    mgs = re.findall(r"^      <MeasureGroup>.*?^      </MeasureGroup>", b, re.S | re.M)
    parts_xml = []
    for mg in mgs:
        mg_id = id_de(mg)
        p = re.search(r"^        <Partitions>.*?^        </Partitions>\n", mg, re.S | re.M).group(0)
        # TableBinding -> DsvTableBinding (formato que usa el disenador)
        p = re.sub(r'<Source xsi:type="TableBinding">\s*<DataSourceID>.*?</DataSourceID>\s*<DbSchemaName>(.*?)</DbSchemaName>\s*<DbTableName>(.*?)</DbTableName>\s*</Source>',
                   lambda m: f'<Source xsi:type="DsvTableBinding">\n                <DataSourceViewID>{DSV_ID}</DataSourceViewID>\n                <TableID>{m.group(1)}_{m.group(2)}</TableID>\n              </Source>', p, flags=re.S)
        parts_xml.append(f"    <MeasureGroup>\n      <ID>{mg_id}</ID>\n" + desindentar(p, 2).rstrip() + "\n    </MeasureGroup>")
        b = b.replace(p, "")
    nom = nombre_archivo(cubo_id)
    items["cube"].append(guardar(nom + ".cube", con_ns(b, "Cube")))
    guardar(nom + ".partitions", f"<Cube {NS} {dtn()} {DEF}>\n  <ID>{cubo_id}</ID>\n  <MeasureGroups>\n" + "\n".join(parts_xml) + "\n  </MeasureGroups>\n</Cube>\n")
    PARTS = nom + ".partitions"

# ---- Estructuras de mineria: la extension Analysis Services Projects 4.0 (VS 2022/2026) ya no tiene
#      disenador de mineria, por eso la mineria se define en el proyecto C# (CuboSiniestrosViales.CSharp)
#      y no se agregan archivos .dmm al proyecto SSAS.

# ---- Roles (sin miembros: al desplegar se conservan los miembros existentes en el servidor)
for b in bloques("Role", 8):
    b = desindentar(b, 8)
    b = re.sub(r"\s*<Members>.*?</Members>", "", b, flags=re.S)
    items["role"].append(guardar(nombre_archivo(id_de(b)) + ".role", con_ns(b, "Role")))

# ---- Base de datos (incluye permisos de base del rol)
dbp = re.search(r"^      <DatabasePermissions>.*?^      </DatabasePermissions>", txt, re.S | re.M)
dbp = desindentar(dbp.group(0), 4) if dbp else ""
guardar("SiniestrosVialesOLAP.database", f"""<Database {NS} {dtn()} {DEF}>
  <ID>SiniestrosVialesOLAP</ID>
  <Name>SiniestrosVialesOLAP</Name>
  <ddl200:CompatibilityLevel>1100</ddl200:CompatibilityLevel>
  <Language>11274</Language>
  <DataSourceImpersonationInfo>
    <ImpersonationMode>Default</ImpersonationMode>
    <ImpersonationInfoSecurity>Unchanged</ImpersonationInfoSecurity>
  </DataSourceImpersonationInfo>
{dbp}
</Database>
""")

def pi(nombre, dep=None):
    d = f"\n      <Dependencies>\n        <ProjectItem>\n          <Name>{dep}</Name>\n          <FullPath>{dep}</FullPath>\n        </ProjectItem>\n      </Dependencies>" if dep else ""
    return f"    <ProjectItem>\n      <Name>{nombre}</Name>\n      <FullPath>{nombre}</FullPath>{d}\n    </ProjectItem>"

guardar(f"{PROY}.dwproj", f"""<Project {NS}>
  <ProductVersion>17.0.0.0</ProductVersion>
  <SchemaVersion>9.0.2.10</SchemaVersion>
  <Database>
    <Name>SiniestrosVialesOLAP.database</Name>
    <FullPath>SiniestrosVialesOLAP.database</FullPath>
  </Database>
  <Cubes>
{chr(10).join(pi(c, PARTS) for c in items["cube"])}
  </Cubes>
  <Dimensions>
{chr(10).join(pi(d) for d in items["dim"])}
  </Dimensions>
  <DataSources>
{chr(10).join(pi(d) for d in items["ds"])}
  </DataSources>
  <DataSourceViews>
{chr(10).join(pi(d) for d in items["dsv"])}
  </DataSourceViews>
  <Roles>
{chr(10).join(pi(r) for r in items["role"])}
  </Roles>
  <Configurations>
    <Configuration>
      <Name>Development</Name>
      <Options>
        <ConnectionMappings>
          <ConfigurationSetting>
            <Id>{DS_ID}</Id>
            <Name>{DS_ID}</Name>
            <Value xsi:type="xsd:string">{DS_CONN}</Value>
          </ConfigurationSetting>
        </ConnectionMappings>
        <ConnectionSecurityMappings>
          <ConfigurationSetting>
            <Id>{DS_ID}</Id>
            <Name>{DS_ID}</Name>
            <Value xsi:type="xsd:int">0</Value>
          </ConfigurationSetting>
        </ConnectionSecurityMappings>
      </Options>
    </Configuration>
  </Configurations>
</Project>
""")

guardar(f"{PROY}.dwproj.user", f"""<AnalysisServicesUserConfiguration {NS}>
  <Configurations>
    <Configuration>
      <Name>Development</Name>
      <Options>
        <TargetServer>{SERVIDOR}</TargetServer>
        <TargetDatabase>SiniestrosVialesOLAP_Diseno</TargetDatabase>
        <StartObject>
          <ObjectId></ObjectId>
          <ObjectType>Current</ObjectType>
        </StartObject>
      </Options>
    </Configuration>
  </Configurations>
</AnalysisServicesUserConfiguration>
""")

pg = "{" + str(uuid.uuid4()).upper() + "}"; sg = "{" + str(uuid.uuid4()).upper() + "}"
cg = "{" + str(uuid.uuid4()).upper() + "}"   # proyecto C#
with open(os.path.join(ROOT, "visual_studio", f"{PROY}.sln"), "w", encoding="utf-8-sig", newline="\r\n") as f:
    f.write(f"""
Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio Version 17
VisualStudioVersion = 17.14.36414.22
MinimumVisualStudioVersion = 10.0.40219.1
Project("{{9A19103F-16F7-4668-BE54-9A1E7A4F7556}}") = "{PROY}.CSharp", "{PROY}.CSharp\\{PROY}.CSharp.csproj", "{cg}"
EndProject
Project("{{D2ABAB84-BF74-430A-B69E-9DC6D40DDA17}}") = "{PROY}", "{PROY}\\{PROY}.dwproj", "{pg}"
EndProject
Global
	GlobalSection(SolutionConfigurationPlatforms) = preSolution
		Development|Default = Development|Default
	EndGlobalSection
	GlobalSection(ProjectConfigurationPlatforms) = postSolution
		{pg}.Development|Default.ActiveCfg = Development
		{pg}.Development|Default.Build.0 = Development
		{pg}.Development|Default.Deploy.0 = Development
		{cg}.Development|Default.ActiveCfg = Debug|x64
		{cg}.Development|Default.Build.0 = Debug|x64
	EndGlobalSection
	GlobalSection(SolutionProperties) = preSolution
		HideSolutionNode = FALSE
	EndGlobalSection
	GlobalSection(ExtensibilityGlobals) = postSolution
		SolutionGuid = {sg}
	EndGlobalSection
EndGlobal
""")
print("Proyecto generado en", os.path.join(ROOT, "visual_studio"))
for k, v in items.items(): print(k, v)
