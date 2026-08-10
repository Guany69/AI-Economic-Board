"""econ — CLI for the AI Economic Board simulation service.

Commands:
  econ serve                                    start the API service
  econ variables                                list supported variables
  econ simulate <VAR> --type T --value V        submit a simulation
  econ status <RUN_ID>                          check a run's status
  econ result <RUN_ID>                          show the full result
  econ baseline-create [--name N]               build + persist a Fair baseline (local)
"""

import argparse
import logging
import sys


def _default_base_url() -> str:
    from app.config.settings import get_settings
    s = get_settings()
    return f"http://{s.api_host}:{s.api_port}"


def cmd_serve(args) -> int:
    import uvicorn
    from app.config.settings import get_settings
    s = get_settings()
    uvicorn.run("app.presentation.api.main:app", host=s.api_host, port=s.api_port,
                log_level="info")
    return 0


def cmd_variables(args) -> int:
    from app.presentation.cli.client import ApiClient
    from app.presentation.cli.render import render_variables
    print(render_variables(ApiClient(args.url).variables()))
    return 0


def cmd_simulate(args) -> int:
    from app.presentation.cli.client import ApiClient
    from app.presentation.cli.render import render_result
    client = ApiClient(args.url)
    sub = client.submit(args.variable, args.type, args.value)
    run_id = sub["simulation_run_id"]
    print(f"Submitted: {run_id} ({sub['status']})")
    if args.wait:
        data = client.wait(run_id)
        print()
        print(render_result(data))
        return 0 if data["status"] == "COMPLETED" else 1
    print(f"Check with: econ result {run_id}")
    return 0


def cmd_status(args) -> int:
    from app.presentation.cli.client import ApiClient
    data = ApiClient(args.url).result(args.run_id)
    print(f"{data['simulation_run_id']}: {data['status']}")
    if data.get("error"):
        print(f"  [{data['error']['type']}] {data['error']['message']}")
    return 0


def cmd_result(args) -> int:
    from app.presentation.cli.client import ApiClient
    from app.presentation.cli.render import render_result
    print(render_result(ApiClient(args.url).result(args.run_id)))
    return 0


def cmd_baseline_create(args) -> int:
    logging.basicConfig(level=logging.INFO)
    from app.infrastructure.fair.baseline import create_baseline
    from app.presentation.api.main import run_migrations
    run_migrations()
    baseline_id = create_baseline(args.name)
    print(f"Baseline created (id={baseline_id})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="econ", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=None, help="API base URL")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="start the API service").set_defaults(fn=cmd_serve)
    sub.add_parser("variables", help="list supported variables").set_defaults(fn=cmd_variables)

    p = sub.add_parser("simulate", help="submit a simulation")
    p.add_argument("variable", help="economic variable id (see: econ variables)")
    p.add_argument("--type", required=True, choices=["ABSOLUTE", "PERCENT", "SET_VALUE"])
    p.add_argument("--value", required=True)
    p.add_argument("--wait", action="store_true", help="wait for completion and print the result")
    p.set_defaults(fn=cmd_simulate)

    p = sub.add_parser("status", help="check a run's status")
    p.add_argument("run_id")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("result", help="show a run's full result")
    p.add_argument("run_id")
    p.set_defaults(fn=cmd_result)

    p = sub.add_parser("baseline-create", help="build + persist a Fair baseline (local)")
    p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_baseline_create)

    args = parser.parse_args()
    if args.url is None:
        args.url = _default_base_url()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
