from ModuleFolders.Service.Agent.AgentFacade import AgentFacade

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="AiNiee headless Agent facade")
    parser.add_argument("input_path")
    parser.add_argument("--mode", choices=("plan", "run"), default="plan")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    facade = AgentFacade()
    if args.mode == "run":
        return facade.run(args.input_path, yes=args.yes, mode=args.mode)
    facade.build_plan(args.input_path, mode=args.mode)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
