#!/usr/bin/env python3
"""Query the TripLens logic master without requiring sqlite3 CLI."""

import argparse, csv, json, sqlite3, sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("database",type=Path)
    p.add_argument("--logic-id")
    p.add_argument("--platform")
    p.add_argument("--system")
    p.add_argument("--equipment")
    p.add_argument("--tag-id",help="Return logic linked to this exact Tag Master ID")
    p.add_argument("--search")
    p.add_argument("--enabled",choices=["true","false"])
    p.add_argument("--scope",choices=["active","disabled","all"],default="active",
                   help="Query scope; defaults to active logic only")
    p.add_argument("--limit",type=int,default=50)
    p.add_argument("--format",choices=["json","csv"],default="json")
    a=p.parse_args()
    where=[]; params=[]
    if a.logic_id: where.append("logic_id=?"); params.append(a.logic_id)
    if a.platform: where.append("platform=?"); params.append(a.platform)
    if a.system: where.append("system=?"); params.append(a.system)
    if a.equipment: where.append("equipment LIKE ?"); params.append(f"%{a.equipment}%")
    if a.tag_id:
        where.append("EXISTS (SELECT 1 FROM logic_tag_link x WHERE x.logic_id=logic_rule.logic_id AND x.tag_id=?)")
        params.append(a.tag_id)
    if a.enabled is not None:
        where.append("enabled_default=?"); params.append(int(a.enabled=="true"))
    elif a.scope != "all":
        where.append("enabled_default=?"); params.append(int(a.scope=="active"))
    if a.search:
        where.append("(logic_id LIKE ? OR alarm_text_ko LIKE ? OR derived_signal LIKE ? OR equipment LIKE ?)")
        params.extend([f"%{a.search}%"]*4)
    sql="""SELECT logic_id,platform,system,subsystem,equipment,derived_signal,
           alarm_type,alarm_text_ko,threshold_basis,threshold_value,threshold_unit,
           threshold_direction,delay_s,enabled_default,absolute_conversion_status,
           (SELECT group_concat(DISTINCT x.tag_id)
              FROM logic_tag_link x WHERE x.logic_id=logic_rule.logic_id) AS linked_tag_ids
           FROM logic_rule"""
    if where: sql+=" WHERE "+" AND ".join(where)
    sql+=" ORDER BY platform,system,priority_rank,logic_id LIMIT ?"; params.append(a.limit)
    db=sqlite3.connect(a.database); db.row_factory=sqlite3.Row
    result=[dict(x) for x in db.execute(sql,params)]; db.close()
    if a.format=="json":
        print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        if not result: return
        w=csv.DictWriter(sys.stdout,fieldnames=result[0].keys()); w.writeheader(); w.writerows(result)

if __name__=="__main__":
    main()
