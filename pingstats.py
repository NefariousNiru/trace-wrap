import argparse
import json
import subprocess
import sys
import plotly.graph_objs as pogo


def save_cumulative_stats_json(output, path):
    with open(path, "w") as json_write:
        json.dump(output, json_write, indent=4)

def save_latency_distribution_boxplot_pdf(output, args):
    fig = pogo.Figure()

    fig.add_trace(
        pogo.Box(
            y = [data[-1] for data in output.values()],
            name="Latencies",
            boxpoints='all',
            jitter=0.5,
            pointpos = -1.8
        )
    )

    fig.update_layout(
        title="Latency BoxPlot for Ping" + (f"for Domain: {args.target}" if args.target else ""),
        yaxis_title="Latency (ms)",
        showlegend=False
    )
    fig.write_image(args.graph if args.graph else "./pingstats.pdf", format='pdf')


def parse_ping_output(output, args):
    ping_data = {}
    i = 1
    output = output.split("\n")

    max_ping = args.max_pings if args.max_pings else len(output) - 1

    for ping in output[1: max_ping + 1]:
        parts = ping.split()
        ping_data[f"{i}"] = [parts[3], parts[4], parts[-2].split("=")[-1]]
        i += 1
    return ping_data

def execute_ping(args):
    command = ['ping', args.target]

    if args.run_delay:
        command.extend(['-i', str(args.run_delay)])

    if args.max_pings:
        command.extend(['-c', str(args.max_pings)])

    try:
        '''
        capture_output=True catches either result (output: stdout or error: stderr)
        check=True raises a CalledProcessError if subsystem exit code was non-zero (indicates an error)
        text=True returns output as string instead of bytes
        '''
        ping_output = subprocess.run(command, capture_output=True, text=True, check=True)
        return ping_output.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error executing ping {e}", file=sys.stderr)
        return None


def use_test_directory(args):
    with open(args.test, 'r') as file:
        return file.read()


def unwrap_arguments(argument_parser):
    args = argument_parser.parse_args()
    if not args.max_pings and not args.test:
        print("-m (max_pings) flag not specified, setting default pings = 30")
        args.max_pings = 30

    output = []
    parsed_output = {}
    if args.test:
        output = use_test_directory(args)
        parsed_output = parse_ping_output(output, args)
    else:
        if not args.target:
            argument_parser.error("A target '-t' is required if '--test' is absent)")

        output = execute_ping(args)
        parsed_output = parse_ping_output(output, args)

    if output:
        save_cumulative_stats_json(output, args.output if args.output else "./pingstats.json")
        save_latency_distribution_boxplot_pdf(parsed_output, args)


'''
Program Execution begins in the main function. It parses arguments that are based from the CLI. If --test is specified, it skips every other flag and tests for existing output.
Otherwise based on the flags, it either
'''
def main():
    argument_parser = argparse.ArgumentParser(description='''Welcome to PingWrap.
    This Program acts as a wrapper for Ping, a command line tool that automatically executes Ping multiple times towards a target domain name or IP address''')
    argument_parser.add_argument('-d', '--run-delay', type=int, default=0,
                        help="Number of seconds to wait between two consecutive pings")
    argument_parser.add_argument('-m', '--max-pings', type=int, help="Number of max pings for ping")
    argument_parser.add_argument('-o', '--output', help="Path and name of output JSON file containing the stats")
    argument_parser.add_argument('-g', '--graph', help="Path and name of output PDF file containing stats graph")
    argument_parser.add_argument('-t', '--target', help="A target domain name or IP address (required if --test is absent)")
    argument_parser.add_argument('--test', help='''Directory containing num_pings text files, each of which contains the output of a ping run. 
    If present, this will override all other options and traceroute will not be invoked. Stats will be computed over the ping output stored in the text files''')

    unwrap_arguments(argument_parser)


if __name__ == '__main__':
    main()