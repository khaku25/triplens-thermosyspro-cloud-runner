"""Editable draw.io document generation and stable-ID layout preservation."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import re
import textwrap
from collections import defaultdict
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zlib

from .model import digest, text
from .xmlio import parse_xml, MAX_XML

COLORS = {'source':('#edf5ff','#4381b5'), 'derived':('#fff4dd','#ba861e'),
          'condition':('#eaf6ee','#548766'), 'operation':('#ffffff','#526778'),
          'additional':('#f0ebfa','#8873b1'), 'column_label':('#eaf0f5','#c1cfdb'),
          'title':('#15354f','#15354f'), 'group_label':('#eaf0f5','#c1cfdb'),
          'page_link':('#edf5ff','#4381b5')}
VISUAL_KEYS={'fillColor','strokeColor','fontColor','fontSize','rounded','strokeWidth','dashed'}


def decode_document(xml: str) -> ET.Element:
    root=parse_xml(xml)
    if root.tag!='mxfile':
        raise ValueError('Expected draw.io mxfile document')
    diagrams=root.findall('diagram')
    if len(diagrams)>400:
        raise ValueError('Too many draw.io pages')
    page_ids=set()
    for page in diagrams:
        key=page.get('id')
        if not key or key in page_ids:
            raise ValueError(f'duplicate/missing draw.io page ID: {key}')
        page_ids.add(key)
        if page.find('mxGraphModel') is None:
            try:
                packed=base64.b64decode((page.text or '').strip(),validate=True)
                d=zlib.decompressobj(-15)
                raw=d.decompress(packed,MAX_XML+1)
                if len(raw)>MAX_XML or d.unconsumed_tail or not d.eof:
                    raise ValueError('Oversized compressed draw.io page')
                decoded=unquote(raw.decode('utf-8'))
                page.text=None; page.append(parse_xml(decoded))
            except (ValueError,UnicodeError,zlib.error) as exc:
                raise ValueError(f'Invalid compressed draw.io page: {key}') from exc
        graph=page.find('mxGraphModel/root')
        if graph is None:
            raise ValueError(f'No graph root in page: {key}')
        seen=set()
        if len(graph)>15000:
            raise ValueError('Too many draw.io cells')
        for item in graph:
            item_id=item.get('id')
            if not item_id or item_id in seen:
                raise ValueError(f'duplicate/missing draw.io cell ID: {key}: {item_id}')
            seen.add(item_id)
            cell=item if item.tag=='mxCell' else item.find('mxCell')
            if cell is None:
                raise ValueError('Unknown draw.io cell wrapper')
            for geometry in cell.findall('.//mxGeometry')+cell.findall('.//mxPoint'):
                for attr in ('x','y','width','height'):
                    if geometry.get(attr) is None:
                        continue
                    try:
                        value=float(geometry.get(attr))
                    except ValueError as exc:
                        raise ValueError('Invalid geometry') from exc
                    if not math.isfinite(value) or abs(value)>1_000_000:
                        raise ValueError('Non-finite or excessive geometry')
                    if attr in {'width','height'} and value<=0 and cell.get('vertex')=='1':
                        raise ValueError('Invalid geometry dimensions')
        for item in graph:
            cell=item if item.tag=='mxCell' else item.find('mxCell')
            if cell.get('edge')=='1':
                if cell.get('source') not in seen or cell.get('target') not in seen:
                    raise ValueError(f'Dangling draw.io edge: {key}: {item.get("id")}')
    return root


def validate_layout_schema(document: ET.Element) -> str:
    """Accept only unmixed stable-ID schema 1 or 2 layout documents."""
    schema=document.get('triplens_schema')
    if schema not in {'1','2'}:
        raise ValueError('Unsupported draw.io layout schema; expected 1 or 2')
    ids={item.get('id','') for item in document.iter()}
    legacy=any(key.startswith('logic:') for key in ids)
    modern=any(key.startswith(('condition:','operation:','additional:')) for key in ids)
    if (schema=='1' and modern) or (schema=='2' and legacy):
        raise ValueError('Mixed or mismatched draw.io schema and central IDs')
    prefix='logic:' if schema=='1' else 'operation:'
    if not any(key.startswith(prefix) for key in ids):
        raise ValueError('Numeric-ID preview or missing stable central IDs; not a supported layout')
    return schema


def read_layout(xml: str | None) -> dict:
    result={}
    if not xml:
        return result
    document=decode_document(xml)
    if validate_layout_schema(document)=='1':
        # Reset all legacy positions once: old branches overlap the new headers
        # and additional-information blocks. Stable entity/page IDs remain intact.
        return result
    for page in document.findall('diagram'):
        entries={}
        for item in page.find('mxGraphModel/root'):
            cell=item if item.tag=='mxCell' else item.find('mxCell')
            geometry=cell.find('mxGeometry')
            if geometry is None:
                continue
            entries[item.get('id')]={'geometry':copy.deepcopy(geometry), 'style':cell.get('style',''),
                                     'source':cell.get('source'), 'target':cell.get('target')}
        result[page.get('id')]=entries
    return result


def lines(value: str, width=43) -> str:
    return '\n'.join('\n'.join(textwrap.wrap(line,width=width,break_long_words=True,break_on_hyphens=False))
                     for line in str(value).splitlines())


class Page:
    def __init__(self, parent, page_id, name, rule_ids, layout, version, scope):
        self.page=ET.SubElement(parent,'diagram',{'id':page_id,'name':name,'scope':scope,
            'rule_ids':json.dumps(rule_ids,separators=(',',':')),'semantic_sha256':version})
        self.model=ET.SubElement(self.page,'mxGraphModel',{'dx':'1600','dy':'1000','grid':'1','gridSize':'10',
            'guides':'1','tooltips':'1','connect':'1','arrows':'1','fold':'1','page':'1','pageScale':'1',
            'pageWidth':'1560','pageHeight':'1100','math':'0','shadow':'0'})
        self.root=ET.SubElement(self.model,'root')
        ET.SubElement(self.root,'mxCell',{'id':'0'})
        ET.SubElement(self.root,'mxCell',{'id':'1','parent':'0'})
        self.layout=layout.get(page_id,{})
        self.ids={'0','1'}
        self.max_y=0
        self.max_x=1560

    def vertex(self, key, kind, label, x, y, w, h, **metadata):
        if key in self.ids:
            raise ValueError(f'duplicate generated cell: {key}')
        self.ids.add(key)
        attrs={'id':key,'label':label,'kind':kind,'managed':'1',**{k:text(v) for k,v in metadata.items()}}
        obj=ET.SubElement(self.root,'object',attrs)
        fill,stroke=COLORS.get(kind,COLORS['operation'])
        style={'rounded':'1','whiteSpace':'wrap','html':'0','fontFamily':'Arial','fontSize':'14',
               'align':'left','verticalAlign':'middle','spacing':'12','fillColor':fill,'strokeColor':stroke,
               'fontColor':'#ffffff' if kind=='title' else '#16324f','strokeWidth':'1.5'}
        old=self.layout.get(key,{})
        for item in old.get('style','').split(';'):
            if '=' in item:
                k,v=item.split('=',1)
                if k in VISUAL_KEYS and re.fullmatch(r'[#a-zA-Z0-9.\-]+',v):
                    style[k]=v
        cell=ET.SubElement(obj,'mxCell',{'vertex':'1','parent':'1',
            'style':';'.join(f'{k}={v}' for k,v in style.items())+';'})
        geom=copy.deepcopy(old.get('geometry'))
        if geom is None:
            geom=ET.Element('mxGeometry',{'x':str(x),'y':str(y),'width':str(w),'height':str(h),'as':'geometry'})
        cell.append(geom)
        self.max_y=max(self.max_y,float(geom.get('y','0'))+float(geom.get('height','0'))+70)
        self.max_x=max(self.max_x,float(geom.get('x','0'))+float(geom.get('width','0'))+40)
        return key

    def edge(self, source, target, role='signal'):
        key='edge:'+digest([source,target,role])[:24]
        if key in self.ids:
            raise ValueError(f'duplicate generated edge: {key}')
        self.ids.add(key)
        cell=ET.SubElement(self.root,'mxCell',{'id':key,'parent':'1','edge':'1','source':source,'target':target,
            'value':'','role':role,'style':'edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=block;strokeColor=#607d94;strokeWidth=1.5;'})
        old=self.layout.get(key,{})
        geom=copy.deepcopy(old.get('geometry')) if old.get('source')==source and old.get('target')==target else None
        if geom is None:
            geom=ET.Element('mxGeometry',{'relative':'1','as':'geometry'})
        cell.append(geom)

    def finish(self):
        self.model.set('pageHeight',str(int(max(1100,self.max_y))))
        self.model.set('pageWidth',str(int(self.max_x)))


def build_document(model: dict, layout_xml: str | None = None) -> str:
    layout=read_layout(layout_xml)
    root=ET.Element('mxfile',{'host':'app.diagrams.net','type':'device','compressed':'false',
        'triplens_schema':'2','semantic_sha256':model['semantic_sha256'],
        'verification_scope':'SOURCE_EXISTENCE_ONLY; BEHAVIOUR_STATUS_RETAINED'})
    groups=model['groups']
    screens=defaultdict(list)
    for gid,rules in groups.items():
        for screen in sorted({r['screen'] for r in rules}):
            screens[screen].append((gid,[r for r in rules if r['screen']==screen]))
    defs=[('overview','00 · Logic Master',[],[],'overview')]
    for screen,subgroups in sorted(screens.items()):
        defs.append(('screen:'+digest(screen)[:12],screen,subgroups,
                     [r['rule_id'] for _,rs in subgroups for r in rs],'equipment'))
    for gid,rules in groups.items():
        defs.append((gid,gid+' · '+rules[0]['group'],[(gid,rules)],
                     [r['rule_id'] for r in rules],'input_group'))
    for rule in model['rules']:
        defs.append(('rule:'+rule['rule_id'],rule['rule_id'],[(rule['input_group_id'],[rule])],
                     [rule['rule_id']],'rule'))
    for page_id,name,subgroups,rule_ids,scope in defs:
        page=Page(root,page_id,name,rule_ids,layout,model['semantic_sha256'],scope)
        page.vertex('title','title',f'TripLens  /  {name}\n원장 기반 로직도 · 조건 실행기가 아님',32,24,1480,78)
        if scope=='overview':
            page.vertex('overview-policy','group_label',
                f"{len(model['tags'])} source tags  ·  {len(model['rules'])} rules  ·  {len(groups)} input groups\n"
                '파란 태그 = OPC UA 원천  /  황색 태그 = 등록된 파생 출력\n'
                '태그 존재 확인과 공학적 동작 검증은 별개입니다. UNKNOWN/PARTIAL은 그대로 표시합니다.',
                32,126,1480,118)
            for i,(screen,_) in enumerate(sorted(screens.items())):
                page.vertex('nav:'+digest(screen)[:12],'page_link',screen,32+(i%3)*500,280+(i//3)*120,470,88,
                            target_page='screen:'+digest(screen)[:12])
            page.finish(); continue
        y=130
        for gid,rules in subgroups:
            inputs=rules[0]['inputs']
            height=max(len(inputs)*120,sum(max(250,len(r['outputs'])*114+24) for r in rules))+114
            page.vertex('group:'+gid,'group_label',f'{gid}  ·  공유 입력 {len(inputs)}개  /  분기 {len(rules)}개',
                        32,y,1480,42,group_id=gid)
            for name,x,width in [('INPUT',40,320),('CONDITION',410,320),('OPERATION',780,320),('OUTPUT',1150,360)]:
                page.vertex('column:'+gid+':'+name.lower(),'column_label',name,x,y+54,width,36,group_id=gid)
            sy=y+106
            source_ids=[]
            for i,tag in enumerate(inputs):
                t=model['tags'].get(tag,{})
                is_native=tag in model['tags']
                desc=t.get('description_ko') or t.get('description_en') or '등록된 파생 로직 출력'
                label=('SOURCE INPUT' if is_native else 'DERIVED INPUT')+'\n'+lines(tag,42)+'\n'+lines(desc,42)
                if t.get('unit'):
                    label+='\n단위: '+t['unit']
                sid=page.vertex('source:'+gid+':'+digest(tag)[:16],'source' if is_native else 'derived',
                    label,40,sy+i*120,320,108,tag_id=tag,group_id=gid,is_native=str(is_native).lower())
                source_ids.append((sid,tag))
            by=sy
            for r in rules:
                rid=r['rule_id']; branch_h=max(250,len(r['outputs'])*114+24)
                condition=page.vertex('condition:'+rid,'condition',rid+'\n'+lines(r['condition'],38),
                    410,by,320,108,rule_id=rid,condition=r['condition'],group_id=gid)
                operation=page.vertex('operation:'+rid,'operation',rid+'\n'+lines(r['logic_name'],38)+'\n'+r['logic_type'],
                    780,by,320,108,rule_id=rid,logic_type=r['logic_type'],group_id=gid)
                info='ADDITIONAL INFO\n'+lines('지연: '+(r['delay'] or 'NOT SPECIFIED'),38)
                info+='\n'+lines('복귀/히스테리시스: '+(r['reset_hysteresis'] or 'NOT SPECIFIED'),38)
                info+='\n'+lines('동작 검증(원장): '+(r['validation_status'] or 'NOT SPECIFIED'),38)
                info+='\n'+lines('출력 분류: '+(r['output_class'] or 'NOT SPECIFIED'),38)
                page.vertex('additional:'+rid,'additional',info,780,by+120,320,110,
                    rule_id=rid,delay=r['delay'],reset_hysteresis=r['reset_hysteresis'],
                    validation_status=r['validation_status'],output_class=r['output_class'],group_id=gid)
                for sid,tag in source_ids:
                    page.edge(sid,condition,'reset_input' if 'Reset' in tag else 'input')
                page.edge(condition,operation,'condition')
                for j,tag in enumerate(r['outputs']):
                    is_native=tag in model['tags']; t=model['tags'].get(tag,{})
                    desc=t.get('description_ko') or ('등록된 파생 알람 · OPC UA Node 아님' if not is_native else '')
                    label=('SOURCE OUTPUT' if is_native else 'DERIVED OUTPUT')+'\n'+lines(tag,45)
                    if desc:
                        label+='\n'+lines(desc,45)
                    out=page.vertex('output:'+rid+':'+digest(tag)[:16], 'source' if is_native else 'derived',
                        label,1150,by+j*114,360,102,tag_id=tag,rule_id=rid,is_native=str(is_native).lower(),group_id=gid)
                    page.edge(operation,out,'output')
                by+=branch_h
            y+=height+32
        page.finish()
    xml=ET.tostring(root,encoding='unicode')
    decode_document(xml)  # Re-validate all generated IDs, geometries, and edges.
    return '<?xml version="1.0" encoding="utf-8"?>\n'+xml+'\n'


def create_index(model: dict, xml: str) -> dict:
    """Index actual XML pages/cells; metadata from one validated source revision."""
    pages={}; entities={}; tags=copy.deepcopy(model['tags']); rules={}
    for tag,row in tags.items():
        row['rule_ids']=sorted(r['rule_id'] for r in model['rules'] if tag in r['inputs']+r['outputs'])
        entities[tag]=dict(row)
    for tag,producers in model['derived'].items():
        entities[tag]={'raw_tag_id':tag,'is_native':False,'is_derived':True,'description_ko':'등록된 파생 알람 출력',
                       'unit':'BOOL','rule_ids':sorted(r['rule_id'] for r in model['rules'] if tag in r['inputs']+r['outputs'])}
    for page in decode_document(xml).findall('diagram'):
        p={'id':page.get('id'),'name':page.get('name'),'scope':page.get('scope'),
           'rule_ids':json.loads(page.get('rule_ids','[]')),'tag_cells':defaultdict(list)}
        for obj in page.findall('mxGraphModel/root/object'):
            if obj.get('tag_id'):
                p['tag_cells'][obj.get('tag_id')].append(obj.get('id'))
        p['tag_cells']=dict(p['tag_cells']); pages[p['id']]=p
    for r in model['rules']:
        rid=r['rule_id']; row=dict(r)
        row.update(rule_page='rule:'+rid,group_page=r['input_group_id'],
                   equipment_page='screen:'+digest(r['screen'])[:12],source_existence_status='REGISTERED_SOURCE_RESOLVED')
        rules[rid]=row
    native_inputs={t for r in model['rules'] for t in r['inputs'] if t in tags}
    native_outputs={t for r in model['rules'] for t in r['outputs'] if t in tags}
    counts={'source_tags':len(tags),'rules':len(rules),'input_groups':len(model['groups']),
            'equipment_pages':sum(p['scope']=='equipment' for p in pages.values()),'pages':len(pages),
            'native_inputs':len(native_inputs),'native_outputs':len(native_outputs),'derived_outputs':len(model['derived'])}
    return {'schema_version':2,'semantic_sha256':model['semantic_sha256'],
            'drawio_sha256':hashlib.sha256(xml.encode()).hexdigest(),'counts':counts,
            'pages':pages,'rules':rules,'tags':tags,'entities':entities,
            'policy':'DRAWING_OF_REGISTERED_RULES; NOT_EXECUTABLE_PROTECTION; LIVE_EXISTENCE_IS_NOT_BEHAVIOURAL_VALIDATION'}
