"""Fixed, JSON-only CLI for Semantic Bridge's isolated background Chrome lane."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from browser_lane.cdp_lane import BrowserLane

def main(argv=None):
    parser=argparse.ArgumentParser(description="Background browser control without keyboard or focus")
    sub=parser.add_subparsers(dest="op",required=True)
    for name in ("start","list","shutdown"):
        sub.add_parser(name)
    new=sub.add_parser("new");new.add_argument("url")
    nav=sub.add_parser("navigate");nav.add_argument("tab_id");nav.add_argument("url")
    read=sub.add_parser("read");read.add_argument("tab_id")
    click=sub.add_parser("click");click.add_argument("tab_id");click.add_argument("selector")
    fill=sub.add_parser("fill");fill.add_argument("tab_id");fill.add_argument("selector")
    end=sub.add_parser("close");end.add_argument("tab_id")
    args=parser.parse_args(argv)
    lane=BrowserLane()
    try:
        if args.op=="start":value=lane.start()
        elif args.op=="list":value=lane.list()
        elif args.op=="shutdown":value=lane.shutdown()
        elif args.op=="new":value=lane.new(args.url)
        elif args.op=="navigate":value=lane.navigate(args.tab_id,args.url)
        elif args.op=="read":value=lane.read(args.tab_id)
        elif args.op=="click":value=lane.click(args.tab_id,args.selector)
        elif args.op=="fill":
            value=sys.stdin.read(10001)
            if len(value)>10000:raise ValueError("input too long")
            value=lane.fill(args.tab_id,args.selector,value)
        elif args.op=="close":value=lane.close(args.tab_id)
        else:raise ValueError("unknown operation")
        print(json.dumps({"ok":True,"result":value},ensure_ascii=True))
        return 0
    except (OSError,RuntimeError,ValueError,KeyError,PermissionError,TimeoutError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__,"reason":str(exc)[:200]},ensure_ascii=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())