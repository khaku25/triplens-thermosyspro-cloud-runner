"""Small bounded XML/OOXML reader for exported authoring tables (no Excel engine)."""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import zipfile
import xml.etree.ElementTree as ET

NS = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
MAX_XML=25_000_000


def parse_xml(data: bytes | str) -> ET.Element:
    if isinstance(data,str):
        data=data.encode('utf-8')
    if len(data)>MAX_XML or re.search(br'<!\s*(DOCTYPE|ENTITY)',data,re.I):
        raise ValueError('Unsafe or oversized XML/DTD/entity payload')
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f'Invalid XML: {exc}') from exc


def read_table(path: Path, sheet: str | None = None, key: str | None = None) -> list[dict]:
    if path.suffix.lower()=='.csv':
        with path.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream)
            headers=reader.fieldnames or []
            if not headers or len(set(headers))!=len(headers):
                raise ValueError(f'Invalid/duplicate CSV headers: {path.name}')
            rows=list(reader)
            if any(None in r for r in rows):
                raise ValueError(f'CSV has too many columns: {path.name}')
            return [r for r in rows if (str(r.get(key,'')).strip() if key else any(r.values()))]
    if path.suffix.lower()!='.xlsx':
        raise ValueError(f'Unsupported authoring file: {path.name}')
    with zipfile.ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist())>MAX_XML*3:
            raise ValueError('Workbook expanded size limit exceeded')
        def xml(name):
            if archive.getinfo(name).file_size>MAX_XML:
                raise ValueError('Workbook XML part too large')
            return parse_xml(archive.read(name))
        wb=xml('xl/workbook.xml')
        relations=xml('xl/_rels/workbook.xml.rels')
        rels={r.get('Id'):r.get('Target') for r in relations}
        sheets=wb.find('m:sheets',NS)
        found=next((s for s in sheets if s.get('name')==sheet),None)
        if found is None:
            raise ValueError(f'Missing worksheet {sheet!r} in {path.name}')
        target=rels[found.get('{'+NS['r']+'}id')]
        name=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        name=str(PurePosixPath(name))
        if '..' in PurePosixPath(name).parts:
            raise ValueError('Unsafe workbook relationship')
        shared=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared=[''.join(n.itertext()) for n in xml('xl/sharedStrings.xml')]
        table=[]
        for row in xml(name).findall('m:sheetData/m:row',NS):
            values={}
            for cell in row.findall('m:c',NS):
                letters=re.sub(r'\d','',cell.get('r',''))
                col=0
                for c in letters:
                    col=col*26+ord(c)-64
                if col<1 or col>200:
                    continue
                if cell.find('m:f',NS) is not None:
                    raise ValueError(f'Formula in authoring data {sheet}!{cell.get("r")}; export literal values first')
                kind=cell.get('t')
                raw=cell.findtext('m:v','',NS)
                if kind=='s':
                    value=shared[int(raw)] if raw else ''
                elif kind=='inlineStr':
                    element=cell.find('m:is',NS)
                    value=''.join(element.itertext()) if element is not None else ''
                elif kind=='e':
                    raise ValueError(f'Excel error at {sheet}!{cell.get("r")}: {raw}')
                elif kind=='b':
                    value='TRUE' if raw=='1' else 'FALSE'
                else:
                    value=raw
                values[col-1]=value
            if values:
                table.append([values.get(i,'') for i in range(max(values)+1)])
        if not table:
            raise ValueError(f'Empty authoring worksheet: {sheet}')
        headers=table[0]
        while headers and not headers[-1]:
            headers.pop()
        if not headers or len(set(headers))!=len(headers):
            raise ValueError(f'Missing/duplicate worksheet headers: {sheet}')
        result=[]
        for values in table[1:]:
            row={h:values[i] if i<len(values) else '' for i,h in enumerate(headers)}
            if key and not row.get(key):
                continue
            if not any(row.values()):
                continue
            result.append(row)
        return result


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields=fields or (list(rows[0]) if rows else [])
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)


def write_xlsx(path: Path, sheets: dict[str,list[dict]]) -> None:
    """Write generated read-only views as standard inline-string OOXML; no formulas."""
    main=NS['m']; rel=NS['r']
    wb=ET.Element('workbook',{'xmlns':main,'xmlns:r':rel})
    shlist=ET.SubElement(wb,'sheets')
    package_rel='http://schemas.openxmlformats.org/package/2006/relationships'
    wb_rels=ET.Element('Relationships',{'xmlns':package_rel})
    types=ET.Element('Types',{'xmlns':'http://schemas.openxmlformats.org/package/2006/content-types'})
    ET.SubElement(types,'Default',{'Extension':'rels','ContentType':'application/vnd.openxmlformats-package.relationships+xml'})
    ET.SubElement(types,'Default',{'Extension':'xml','ContentType':'application/xml'})
    ET.SubElement(types,'Override',{'PartName':'/xl/workbook.xml','ContentType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'})
    def colname(n):
        s=''
        while n:
            n,r=divmod(n-1,26); s=chr(65+r)+s
        return s
    def data(element):
        return ET.tostring(element,encoding='utf-8',xml_declaration=True)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        def put(name,content):
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,content)
        for num,(name,rows) in enumerate(sheets.items(),1):
            if len(name)>31:
                raise ValueError('Worksheet name too long')
            fields=list(rows[0]) if rows else ['status']
            ET.SubElement(shlist,'sheet',{'name':name,'sheetId':str(num),'r:id':f'rId{num}'})
            ET.SubElement(wb_rels,'Relationship',{'Id':f'rId{num}','Type':rel+'/worksheet','Target':f'worksheets/sheet{num}.xml'})
            ET.SubElement(types,'Override',{'PartName':f'/xl/worksheets/sheet{num}.xml','ContentType':'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
            sh=ET.Element('worksheet',{'xmlns':main})
            views=ET.SubElement(sh,'sheetViews'); view=ET.SubElement(views,'sheetView',{'workbookViewId':'0'})
            ET.SubElement(view,'pane',{'ySplit':'1','topLeftCell':'A2','activePane':'bottomLeft','state':'frozen'})
            cols=ET.SubElement(sh,'cols')
            for i,key in enumerate(fields,1):
                width=38 if any(w in key.lower() for w in ('input','output','condition','description','notes','source')) else 24
                ET.SubElement(cols,'col',{'min':str(i),'max':str(i),'width':str(width),'customWidth':'1'})
            sd=ET.SubElement(sh,'sheetData')
            matrix=[fields]+[[r.get(k,'') for k in fields] for r in rows]
            for rownum,values in enumerate(matrix,1):
                rr=ET.SubElement(sd,'row',{'r':str(rownum),'ht':'34' if rownum==1 else '44','customHeight':'1'})
                for i,value in enumerate(values,1):
                    c=ET.SubElement(rr,'c',{'r':f'{colname(i)}{rownum}','s':'1' if rownum==1 else '2','t':'inlineStr'})
                    tt=ET.SubElement(ET.SubElement(c,'is'),'t',{'xml:space':'preserve'})
                    tt.text='' if value is None else str(value)
            ET.SubElement(sh,'autoFilter',{'ref':f'A1:{colname(len(fields))}{len(matrix)}'})
            put(f'xl/worksheets/sheet{num}.xml',data(sh))
        styles=b'''<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="10"/><name val="Aptos"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf fontId="0" fillId="0" borderId="0" xfId="0"/><xf fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf><xf fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf></cellXfs></styleSheet>'''
        ET.SubElement(wb_rels,'Relationship',{'Id':'rIdStyles','Type':rel+'/styles','Target':'styles.xml'})
        ET.SubElement(types,'Override',{'PartName':'/xl/styles.xml','ContentType':'application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml'})
        rr=ET.Element('Relationships',{'xmlns':package_rel})
        ET.SubElement(rr,'Relationship',{'Id':'rId1','Type':rel+'/officeDocument','Target':'xl/workbook.xml'})
        put('[Content_Types].xml',data(types)); put('_rels/.rels',data(rr))
        put('xl/workbook.xml',data(wb)); put('xl/_rels/workbook.xml.rels',data(wb_rels)); put('xl/styles.xml',styles)
