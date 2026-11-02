"""Build the optional expansion and, with --base-place, an additive Roblox place."""
from pathlib import Path
import argparse,hashlib,json,re,zipfile,xml.etree.ElementTree as ET
from tools.rbxl_addon import add_expansion,standalone_base
APP=Path(__file__).resolve().parent
ROOT=APP.parent
counter=0

def item(parent,cls,name,props=None):
    global counter
    counter+=1
    e=ET.SubElement(parent,'Item',{'class':cls,'referent':f'RBX{counter:08X}'})
    p=ET.SubElement(e,'Properties');ET.SubElement(p,'string',{'name':'Name'}).text=name
    for typ,key,value in props or []:
        v=ET.SubElement(p,typ,{'name':key})
        if isinstance(value,dict):
            for k,n in value.items():ET.SubElement(v,k).text=str(n)
        else:v.text=str(value).lower()if isinstance(value,bool)else str(value)
    return e

def source(parent,path,disabled=False):
    path=Path(path);name=path.name.split('.')[0]
    cls='Script'if '.server.'in path.name else 'LocalScript'if '.client.'in path.name else 'ModuleScript'
    props=[('ProtectedString','Source',path.read_text())]
    if cls!='ModuleScript':props.append(('bool','Disabled',disabled))
    return item(parent,cls,name,props)

def tree(parent,disabled=False):
    replicated=item(parent,'Folder','BackseatExpedition')
    shared=item(replicated,'Folder','Shared')
    for p in sorted((APP/'src/Shared').glob('*.lua')):source(shared,p)
    remotes=item(replicated,'Folder','Remotes')
    for name,cls in [('Action','RemoteEvent'),('Request','RemoteFunction'),('State','RemoteEvent'),('Input','UnreliableRemoteEvent')]:item(remotes,cls,name)
    server=item(parent,'Folder','BackseatExpeditionServer')
    for p in sorted((APP/'src/Server').glob('*.lua')):source(server,p,disabled)
    client=item(parent,'Folder','BackseatExpeditionClient')
    for p in sorted((APP/'src/Client').glob('*.lua')):source(client,p,disabled)
    return replicated,server,client

def xml_root():
    root=ET.Element('roblox',{'version':'4'})
    ET.SubElement(root,'External').text='null';ET.SubElement(root,'External').text='nil'
    return root

def write(path,root):
    ET.indent(root,space='  ')
    path.write_bytes(ET.tostring(root,encoding='utf-8',xml_declaration=True))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-place',type=Path,help='Original RBXL to preserve and extend')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'downloads')
    parser.add_argument('--name',default='Backseat_Rally',help='Artifact label, e.g. Sakura_Pass')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_]+',args.name):parser.error('--name must contain letters, numbers or underscores')
    stem='DM_'+args.name
    version=re.search(r"Version='([^']+)'",(APP/'src/Shared/Config.lua').read_text()).group(1)
    downloads=args.output_dir;downloads.mkdir(parents=True,exist_ok=True)
    place=xml_root()
    world=item(place,'Workspace','Workspace',[('bool','StreamingEnabled',True),('float','Gravity',130)])
    preview=item(world,'Folder','ExpeditionPreview')
    item(preview,'Part','PreviewFloor',[
        ('bool','Anchored',True),('Vector3','size',dict(X=160,Y=2,Z=150)),
        ('CoordinateFrame','CFrame',dict(X=0,Y=-1,Z=0,R00=1,R01=0,R02=0,R10=0,R11=1,R12=0,R20=0,R21=0,R22=1)),
        ('Color3','Color',dict(R=.21,G=.25,B=.22))])
    item(preview,'SpawnLocation','PreviewSpawn',[('bool','Anchored',True),('float','Transparency',1),('bool','Neutral',True)])
    rs=item(place,'ReplicatedStorage','ReplicatedStorage');sss=item(place,'ServerScriptService','ServerScriptService')
    item(place,'ServerStorage','ServerStorage');item(place,'ReplicatedFirst','ReplicatedFirst');item(place,'StarterGui','StarterGui')
    sp=item(place,'StarterPlayer','StarterPlayer');sps=item(sp,'StarterPlayerScripts','StarterPlayerScripts');item(sp,'StarterCharacterScripts','StarterCharacterScripts')
    item(place,'Lighting','Lighting',[('float','ClockTime',15.8),('float','Brightness',2),('Color3','Ambient',dict(R=.40,G=.45,B=.41)),('Color3','OutdoorAmbient',dict(R=.56,G=.59,B=.51))])
    temp=ET.Element('Temp');shared,server,client=tree(temp)
    rs.append(shared);sss.append(server);sps.append(client)
    write(downloads/'Backseat_Rally_Expedition.rbxlx',place)
    standalone=f'DM_Rally_Standalone_v{version}.rbxlx'
    write(downloads/standalone,place)
    standalone_binary=f'DM_Rally_Standalone_v{version}.rbxl'
    binary,_=add_expansion(standalone_base(),APP/'src')
    (downloads/standalone_binary).write_bytes(binary)
    model=xml_root();top=item(model,'Model','BackseatRallyExpansion');source(top,APP/'src/Installer.lua')
    payload=item(top,'Folder','Payload');tree(payload,True)
    write(downloads/'Backseat_Rally_Expansion.rbxmx',model)
    extras=[];aliases=[]
    if args.base_place:
        result,report=add_expansion(args.base_place.read_bytes(),APP/'src')
        place_name=stem+'.rbxl'
        report_name='DM_PRESERVATION.json'if args.name=='Backseat_Rally'else stem+'_PRESERVATION.json'
        (downloads/place_name).write_bytes(result)
        aliases=[f'{stem}_v{version}.rbxl']
        (downloads/aliases[0]).write_bytes(result)
        (downloads/report_name).write_text(json.dumps(report,indent=2)+'\n')
        extras=[place_name,report_name]
    paths=sorted(p for p in APP.rglob('*')if p.is_file()and 'private'not in p.relative_to(APP).parts and '__pycache__'not in p.parts and p.suffix!='.pyc'and p.name!='SOURCE_HASHES.json')
    contents={str(p.relative_to(ROOT)):p.read_bytes()for p in paths}
    for name in ['Backseat_Rally_Expedition.rbxlx','Backseat_Rally_Expansion.rbxmx',standalone,standalone_binary]+extras:contents[name]=(downloads/name).read_bytes()
    contents['START_HERE.txt']=(
        f'1. Open {stem+".rbxl" if args.base_place else standalone_binary} directly in Roblox Studio.\n'
        '2. Press Play. Keep the first car selected, then click TAKE THE ROAD.\n'
        '3. W/A/S/D drive, Space handbrake, R recover, T service at checkpoint bays.\n'
        '4. Driving is cockpit-only. F4 settings/bindings; H headlights.\n'
        '5. RACE FRIENDS hosts a shared-start time trial; friends must join this server.\n'
        '6. Replays: C camera, P pause, comma/period seek; freecam uses WASD/Q/E.\n\n'
        'This clean place uses its own server and native car/map geometry.\n'
        'Publishing, cloud-save access and private imported assets are optional.\n'
        'Offline replays last for this server session.\n\n'
        f'{stem}.rbxl contains the preserved uploaded scene plus the same new driving system.\n'
        'Use the new rally menu to drive; the original backend is incomplete.\n'
        'Fourteen narrow startup Source repairs have exact backups in ServerStorage.\n'
        'The preservation report lists those changes; all original objects/hierarchies remain.\n'
        f'{standalone_binary} isolates the new game from original scene/assets.\n'
    ).encode()
    hashes={name:hashlib.sha256(data).hexdigest()for name,data in contents.items()}
    contents['SOURCE_HASHES.json']=(json.dumps(hashes,indent=2)+'\n').encode()
    zip_name=stem+'.zip'
    with zipfile.ZipFile(downloads/zip_name,'w',zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for name,data in contents.items():
            entry=zipfile.ZipInfo(name,(2026,11,2,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16;z.writestr(entry,data)
    print(json.dumps({n:{'bytes':(downloads/n).stat().st_size,'sha256':hashlib.sha256((downloads/n).read_bytes()).hexdigest()}for n in ['Backseat_Rally_Expedition.rbxlx','Backseat_Rally_Expansion.rbxmx',standalone,standalone_binary,zip_name]+extras+aliases},indent=2))
if __name__=='__main__':main()
