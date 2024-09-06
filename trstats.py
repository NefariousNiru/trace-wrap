import json
import os
import subprocess
import argparse
import sys
import time
import statistics
from collections import defaultdict
from typing import List
import plotly.graph_objs as pogo


class TracerouteOutput:
    def __init__(self, avg, hop, hosts, maximum, median, minimum):
        self.avg = avg
        self.hop = hop
        self.hosts = hosts
        self.maximum = maximum
        self.median = median
        self.minimum = minimum


def get_statistics_per_hop(cumulative_data: List[List[TracerouteOutput]]) -> List[dict]:
    hop_data = {}

    # Grouping data by hop number
    for run in cumulative_data:
        for result in run:
            hop = result.hop
            if hop not in hop_data:
                hop_data[hop] = {
                    'avg': [],
                    'max': [],
                    'med': [],
                    'min': [],
                    'hosts': []  # Assuming hosts remain consistent per hop
                }
            if result.avg:
                hop_data[hop]['avg'].append(result.avg)
                hop_data[hop]['max'].append(result.maximum)
                hop_data[hop]['med'].append(result.median)
                hop_data[hop]['min'].append(result.minimum)
                hop_data[hop]['hosts'].append(result.hosts)

    # Calculate statistics for each hop
    stats_by_hop = []

    for hop, data in hop_data.items():
        hop_stats = {
            'avg': round(statistics.mean(data['avg']),3) if data['avg'] else None,
            'hop': hop,
            'hosts': data['hosts'],
            'max': round(max(data['max']), 3) if data['max'] else None,
            'med': round(statistics.median(data['med']), 3) if data['med'] else None,
            'min': round(min(data['min']), 3) if data['min'] else None
        }

        stats_by_hop.append(hop_stats)

    # Sort the result by hop number
    stats_by_hop.sort(key=lambda x: int(x['hop']))

    return stats_by_hop


#  Saves the output as a JSON file
def save_cumulative_stats_json(output, path):
    with open(path, "w") as json_write:
        json.dump(output, json_write, indent=4)


# Save the output as box plots (latency distribution per each hop) in PDF
def save_latency_distribution_boxplot_pdf(hop_data, args):
    hop_data = {k: hop_data[k] for k in sorted(hop_data, key=lambda x: int(x))}

    fig = pogo.Figure()

    for hop_number, latencies in hop_data.items():
        fig.add_trace(pogo.Box(
            y=latencies,
            name=f"Hop {hop_number}",
            boxpoints='all',  # Show all data points
            jitter=0.5,  # Spread them out so they don't overlap
            pointpos=-1.8  # Position of points on the box plot
        ))

    fig.update_layout(
        title="Latency Distribution per Hop " + (f"for Domain: {args.target}" if args.target else ""),
        xaxis_title="Hop",
        yaxis_title="Latency (ms)",
        showlegend=True
    )

    fig.write_image(args.graph if args.graph else "./trstats.pdf", format='pdf')


# Parses the output from traceroute subroutine and returns a list of TracerouteOutput object
def parse_traceroute_output(traceroute_data, latencies_per_hop) -> List[TracerouteOutput]:
    hops = traceroute_data.splitlines()[1:] # Skips the traceroute header
    parsed_output = []

    for hop in hops:
        parts = hop.split()
        hop_number = parts[0]

        if parts[1:4] == ["*"] * 3:
            parsed_output.append(TracerouteOutput(avg=None, hop=hop_number, hosts=[], maximum=None, median=None, minimum=None))
            continue

        times = []
        hosts = []

        for i in range(1, len(parts)):
            part = parts[i]
            # This is an IP
            if '(' in part and ')' in part:
                host = parts[i - 1]
                hosts.append([host, part])
            #  This is latency
            elif 'ms' in part:
                try:
                    times.append(float(parts[i-1]))
                except ValueError:
                    continue

        # Stats over three probes
        if times:
            avg = round(sum(times) / len(times), 2)
            maximum = max(times)
            minimum = max(times)
            median = statistics.median(times)

            # Creates list of every latency per hop
            latencies_per_hop[hop_number] = latencies_per_hop.get(hop_number, []) + times

            parsed_output.append(TracerouteOutput(avg=avg, hop=hop_number, hosts=hosts, maximum=maximum, median=median, minimum=minimum))

    return parsed_output


#  Executes the subroutine for traceroute
def execute_traceroute_subroutine(target, max_hops=None):
    command = ['traceroute', target, '-m', str(max_hops)] if max_hops else ['traceroute', target]

    try:
        '''
        capture_output=True catches either result (output: stdout or error: stderr)
        check=True raises a CalledProcessError if subsystem exit code was non-zero (indicates an error)
        text=True returns output as string instead of bytes
        '''
        traceroute_output = subprocess.run(command, capture_output=True, text=True, check=True)
        return traceroute_output.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error executing traceroute {e}", file=sys.stderr)
        return None


def execute_traceroute(args):
    cumulative_data = []
    latencies_per_hop = defaultdict(list)

    # Run traceroute NUM_RUNS times
    for i in range(args.num_runs):
        print(f"Running traceroute {i + 1} of {args.num_runs}")
        traceroute_data = execute_traceroute_subroutine(args.target, args.max_hops)

        if traceroute_data:
            parsed_output = parse_traceroute_output(traceroute_data, latencies_per_hop)
            cumulative_data.append(parsed_output)

        # Introduce a delay except the last run
        if i < (args.num_runs - 1):
            time.sleep(args.run_delay)

    return cumulative_data, latencies_per_hop


def use_test_directory(path):
    cumulative_data = []
    latencies_per_hop = defaultdict(list)
    for filename in os.listdir(path):
        filepath = os.path.join(path, filename)
        with open(filepath, 'r') as file:
            parsed_output = parse_traceroute_output(file.read(), latencies_per_hop)
            cumulative_data.append(parsed_output)

    return cumulative_data, latencies_per_hop


def unwrap_arguments(argument_parser):
    args = argument_parser.parse_args()

    stats_per_hop = []
    latencies_per_hop = {}

    if args.test:
        cumulative_data, latencies_per_hop = use_test_directory(args.test)
        stats_per_hop = get_statistics_per_hop(cumulative_data)
    else:
        if not args.target:
            argument_parser.error("A target '-t' is required if '--test' is absent)")

        cumulative_data, latencies_per_hop = execute_traceroute(args)
        stats_per_hop = get_statistics_per_hop(cumulative_data)

    if stats_per_hop:
        save_cumulative_stats_json(stats_per_hop, args.output if args.output else "./trstats.json")

    if latencies_per_hop:
        save_latency_distribution_boxplot_pdf(latencies_per_hop, args)


'''
Program Execution begins in the main function. It parses arguments that are based from the CLI. If --test is specified, it skips every other flag and tests for existing output.
Otherwise based on the flags, it either
'''
def main():
    argument_parser = argparse.ArgumentParser(description='''Welcome to TraceWrap.
    This Program acts as a wrapper for traceroute, a command line tool that automatically executes traceroute multiple times towards a target domain name or IP address''')
    argument_parser.add_argument('-n', '--num-runs', type=int, default=1, help="Number of times traceroute will run")
    argument_parser.add_argument('-d', '--run-delay', type=int, default=0,
                        help="Number of seconds to wait between two consecutive runs")
    argument_parser.add_argument('-m', '--max-hops', type=int, help="Number of max hops per traceroute run")
    argument_parser.add_argument('-o', '--output', help="Path and name of output JSON file containing the stats")
    argument_parser.add_argument('-g', '--graph', help="Path and name of output PDF file containing stats graph")
    argument_parser.add_argument('-t', '--target', help="A target domain name or IP address (required if --test is absent)")
    argument_parser.add_argument('--test', help='''Directory containing num_runs text files, each of which contains the output of a traceroute run. 
    If present, this will override all other options and traceroute will not be invoked. Stats will be computed over the traceroute output stored in the text files''')

    unwrap_arguments(argument_parser)


if __name__ == '__main__':
    main()