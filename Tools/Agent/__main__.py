from ModuleFolders.Service.Agent.AgentFacade import AgentFacade

def main() -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description="AiNiee headless Agent facade")
    parser.add_argument("input_path")
    parser.add_argument("--mode", choices=("plan", "run"), default="plan")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--format", choices=("text", "jsonl"), default="text")
    args = parser.parse_args()
    events = []
    facade = AgentFacade(event_sink=events.append)
    if args.mode == "run":
        result = facade.run(args.input_path, yes=args.yes, mode=args.mode,
                            capture_output=(args.format == "jsonl"))
    else:
        plan = facade.build_plan(args.input_path, mode=args.mode)
        result = 0
        if args.format != "jsonl":
            print(json.dumps(plan, ensure_ascii=False, indent=2))
    if args.format == "jsonl":
        for event in events:
            print(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    elif args.mode == "run" and result == 3:
        print("Agent plan requires confirmation; re-run with --yes.")
    return result

if __name__ == "__main__":
    raise SystemExit(main())
